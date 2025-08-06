# 御坂网络弹幕服务
  

一个功能强大的自托管弹幕（Danmaku）聚合与管理服务，兼容 [dandanplay](https://api.dandanplay.net/swagger/index.html) API 规范。

本项目旨在通过刮削主流视频网站的弹幕，为您自己的媒体库提供一个统一、私有的弹幕API。它自带一个现代化的Web界面，方便您管理弹幕库、搜索源、API令牌和系统设置。

## ✨ 核心功能

- **多源刮削**: 自动从 Bilibili、腾讯视频、爱奇艺、优酷等多个来源获取弹幕。
- **智能匹配**: 通过文件名或元数据（TMDB, TVDB等）智能匹配您的影视文件，提供准确的弹幕。
- **Web管理界面**: 提供一个直观的Web UI，用于：
  - 搜索和手动导入弹幕。
  - 管理已收录的媒体库、数据源和分集。
  - 创建和管理供第三方客户端（如 yamby, hills, 小幻影视）使用的API令牌。
  - 配置搜索源的优先级和启用状态。
  - 查看后台任务进度和系统日志。
- **元数据整合**: 支持与 TMDB, TVDB, Bangumi, Douban, IMDb 集成，丰富您的媒体信息。
- **自动化**: 支持通过 Webhook 接收来自 Sonarr, Radarr, Emby 等服务的通知，实现全自动化的弹幕导入。
- **灵活部署**: 提供 Docker 镜像和 Docker Compose 文件，方便快速部署。

## 🚀 快速开始 (使用 Docker Compose)

推荐使用 Docker 和 Docker Compose 进行部署。我们将分两步部署：先部署数据库，再部署应用本身。

### 步骤 1: 部署 MySQL 数据库

1.  在一个合适的目录（例如 `/opt/docker/danmu-api`）下，创建一个名为 `docker-compose.mysql.yml` 的文件，内容如下：

    ```yaml
    # docker-compose.mysql.yml
    version: '3.5'
    services:
      mysql:
        image: mysql:8.1.0-oracle
        restart: always
        privileged: true
        container_name: danmu-mysql
        volumes:
          - ./mysql-data:/var/lib/mysql
          - ./mysql-conf:/etc/mysql/conf.d
          - ./mysql-logs:/logs
        command:
          --character-set-server=utf8mb4
          --collation-server=utf8mb4_general_ci
          --explicit_defaults_for_timestamp=true
        environment:
          # !!! 重要：请务必替换为您的强密码 !!!
          MYSQL_ROOT_PASSWORD: "your_strong_root_password"
          MYSQL_DATABASE: "danmuapi"
          MYSQL_USER: "danmuapi"
          MYSQL_PASSWORD: "your_strong_user_password"
          TZ: "Asia/Shanghai"
        ports:
          - "3306:3306"
    ```

2.  **重要**: 修改文件中的 `MYSQL_ROOT_PASSWORD` 和 `MYSQL_PASSWORD` 为您自己的安全密码。

3.  在 `docker-compose.mysql.yml` 所在目录运行命令启动数据库：
    ```bash
    docker-compose -f docker-compose.mysql.yml up -d
    ```

### 步骤 2: 部署 Misaka Danmu Server 应用

1.  在同一个目录下，创建另一个名为 `docker-compose.app.yml` 的文件，内容如下。

    ```yaml
    # docker-compose.app.yml
    version: '3.8'
    services:
      app:
        # 替换为您自己的Docker Hub用户名和镜像名，或使用本地构建
        image: l429609201/misaka_danmu_server:latest
        container_name: misaka-danmu-server
        restart: unless-stopped
        # 使用主机网络模式，容器将直接使用宿主机的网络。
        # 这意味着容器内的 127.0.0.1 就是宿主机的 127.0.0.1。
        # 应用将直接在宿主机的 7768 端口上可用，无需端口映射。
        # 推荐使用host模式
        network_mode: "host"
        environment:
            PUID=1000
            PGID=1000
          # --- 数据库连接配置 ---
          # '127.0.0.1' 指向宿主机，因为我们使用了主机网络模式
          - DANMUAPI_DATABASE__HOST=127.0.0.1
          - DANMUAPI_DATABASE__PORT=3306
          - DANMUAPI_DATABASE__NAME=danmuapi
          # !!! 重要：请使用您在步骤1中为数据库设置的用户名和密码 !!!
          - DANMUAPI_DATABASE__USER=danmuapi
          - DANMUAPI_DATABASE__PASSWORD=your_strong_user_password
    
          
          # --- 初始管理员配置 ---
          - DANMUAPI_ADMIN__INITIAL_USER=admin
        volumes:
          # 挂载配置文件目录，用于持久化日志等
          - ./config:/app/config
    ```

2.  **重要**:
    -   确保 `DANMUAPI_DATABASE__PASSWORD` 与您在 `docker-compose.mysql.yml` 中设置的 `MYSQL_PASSWORD` 一致。


3.  在同一目录运行命令启动应用：
    ```bash
    docker-compose -f docker-compose.app.yml up -d
    ```

### 步骤 3: 访问和配置

- **访问Web UI**: 打开浏览器，访问 `http://<您的服务器IP>:7768`。
- **初始登录**:
  - 用户名: `admin` (或您在环境变量中设置的值)。
  - 密码: 首次启动时会在容器的日志中生成一个随机密码。请使用 `docker logs danmu-api` 查看。
- **开始使用**: 登录后，请先在 "设置" -> "账户安全" 中修改您的密码，然后在 "搜索源" 和 "设置" 页面中配置您的API密钥。

## 客户端配置

### 1. 获取弹幕 Token

- 在 Web UI 的 "弹幕Token" 页面，点击 "添加Token" 来创建一个新的访问令牌。
- 创建后，您会得到一串随机字符，这就是您的弹幕 Token。
- 可通过配置自定义域名之后直接点击复制，会帮你拼接好相关的链接

### 2. 配置弹幕接口

在您的播放器（如 Yamby, Hills, 小幻影视等）的自定义弹幕接口设置中，填入以下格式的地址：

`http://<服务器IP>:<端口>/api/<你的Token>`

-   `<服务器IP>`: 部署本服务的主机 IP 地址。
-   `<端口>`: 部署本服务时设置的端口（默认为 `7768`）。
-   `<你的Token>`: 您在上一步中创建的 Token 字符串。

**示例:**

假设您的服务部署在 `192.168.1.100`，端口为 `7768`，创建的 Token 是 `Q2KHYcveM0SaRKvxomQm`。

-   **对于 Yamby / Hills:**
    在自定义弹幕接口中填写：
    `http://192.168.1.100:7768/api/Q2KHYcveM0SaRKvxomQm`

-   **对于 小幻影视:**
    小幻影视可能需要一个包含 `/api/v2` 的路径，您可以填写：
    `http://192.168.1.100:7768/api/Q2KHYcveM0SaRKvxomQm/api/v2`

> **兼容性说明**: 本服务已对路由进行特殊处理，无论您使用 `.../api/<Token>` 还是 `.../api/<Token>/api/v2` 格式，服务都能正确响应，以最大程度兼容不同客户端。
