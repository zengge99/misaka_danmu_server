from datetime import datetime, timedelta, timezone
from typing import Optional

import aiomysql
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from . import crud, models
from .config import settings
from .database import get_db_pool

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v2/auth/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt.secret_key, algorithm=settings.jwt.algorithm)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    pool: aiomysql.Pool = Depends(get_db_pool)
) -> models.User:
    """
    依赖项：解码JWT，验证其有效性，并获取当前用户。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt.secret_key, algorithms=[settings.jwt.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = models.TokenData(username=username)
    except JWTError:
        # 这将捕获过期的令牌、无效的签名等
        raise credentials_exception
    
    user = await crud.get_user_by_username(pool, username=token_data.username)
    if user is None:
        raise credentials_exception
    
    # 新增：检查客户端提供的令牌是否与数据库中存储的最新令牌匹配
    # 这可以防止旧令牌被重用，并实现“单点登录”或“踢掉其他设备”的效果
    if user.get("token") != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is outdated, please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return models.User.model_validate(user)