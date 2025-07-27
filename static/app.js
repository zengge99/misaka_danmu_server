document.addEventListener('DOMContentLoaded', () => {
    const authView = document.getElementById('auth-view');
    const mainView = document.getElementById('main-view');
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const showRegisterLink = document.getElementById('show-register-link');
    const showLoginLink = document.getElementById('show-login-link');
    const authError = document.getElementById('auth-error');
    const searchForm = document.getElementById('search-form');
    const searchKeywordInput = document.getElementById('search-keyword');
    const resultsList = document.getElementById('results-list');
    const logOutput = document.getElementById('log-output');
    const currentUserSpan = document.getElementById('current-user');
    const logoutBtn = document.getElementById('logout-btn');
    const loader = document.getElementById('loader');
    const changePasswordForm = document.getElementById('change-password-form');
    const passwordChangeMessage = document.getElementById('password-change-message');

    let token = localStorage.getItem('danmu_api_token');

    function log(message) {
        const timestamp = new Date().toLocaleTimeString();
        logOutput.textContent = `[${timestamp}] ${message}\n` + logOutput.textContent;
    }

    function toggleLoader(show) {
        loader.classList.toggle('hidden', !show);
    }

    async function apiFetch(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(url, { ...options, headers });

        // 集中处理认证失败
        if (response.status === 401) {
            logout(); // 执行登出操作
            // 抛出错误，中断后续代码执行
            throw new Error("会话已过期或无效，请重新登录。");
        }

        // 对于非OK响应，尝试解析错误信息
        if (!response.ok) {
            // 尝试将响应体作为JSON解析，如果失败则使用原始文本
            const errorData = await response.json().catch(() => response.text());
            const errorMessage = errorData.detail || errorData || `HTTP error! status: ${response.status}`;
            throw new Error(errorMessage);
        }

        // 对于成功的响应，如果响应体可能为空，先获取文本
        const responseText = await response.text();
        // 如果文本不为空则尝试解析为JSON，否则返回空对象
        return responseText ? JSON.parse(responseText) : {};
    }

    function showView(view) {
        authView.classList.add('hidden');
        mainView.classList.add('hidden');
        if (view === 'auth') {
            authView.classList.remove('hidden');
        } else if (view === 'main') {
            mainView.classList.remove('hidden');
        }
    }

    async function checkLogin() {
        if (!token) {
            showView('auth');
            return;
        }
        try {
            const user = await apiFetch('/api/v2/auth/users/me');
            // 如果apiFetch成功，user对象一定是有效的
            currentUserSpan.textContent = `用户: ${user.username}`;
            showView('main');
        } catch (error) {
            // 此处无需再调用logout()，因为它已在apiFetch中处理
            log(`自动登录失败: ${error.message}`);
        }
    }

    function logout() {
        token = null;
        localStorage.removeItem('danmu_api_token');
        showView('auth');
        log('已登出。');
    }

    // --- Auth Form Switching Logic ---
    showRegisterLink.addEventListener('click', (e) => {
        e.preventDefault();
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
        authError.textContent = '';
    });

    showLoginLink.addEventListener('click', (e) => {
        e.preventDefault();
        registerForm.classList.add('hidden');
        loginForm.classList.remove('hidden');
        authError.textContent = '';
    });

    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        authError.textContent = '';
        const username = document.getElementById('register-username').value;
        const password = document.getElementById('register-password').value;

        try {
            await apiFetch('/api/v2/auth/register', {
                method: 'POST',
                body: JSON.stringify({ username, password }),
            });
            log(`用户 '${username}' 注册成功，请登录。`);
            registerForm.reset();
        } catch (error) {
            authError.textContent = `注册失败: ${error.message}`;
            log(`注册失败: ${error.message}`);
        }
    });

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        authError.textContent = '';
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;

        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        try {
            const data = await fetch('/api/v2/auth/token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData,
            }).then(res => {
                if (!res.ok) throw new Error('用户名或密码错误');
                return res.json();
            });

            token = data.access_token;
            localStorage.setItem('danmu_api_token', token);
            log('登录成功。');
            loginForm.reset();
            await checkLogin();
        } catch (error) {
            authError.textContent = `登录失败: ${error.message}`;
            log(`登录失败: ${error.message}`);
        }
    });

    logoutBtn.addEventListener('click', logout);

    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const keyword = searchKeywordInput.value;
        if (!keyword) return;

        resultsList.innerHTML = '';
        toggleLoader(true);
        log(`正在搜索: ${keyword}`);

        try {
            const data = await apiFetch(`/api/v2/search/provider?keyword=${encodeURIComponent(keyword)}`);
            displayResults(data.results);
            log(`搜索到 ${data.results.length} 个结果。`);
        } catch (error) {
            log(`搜索失败: ${error.message}`);
        } finally {
            toggleLoader(false);
        }
    });

    function displayResults(results) {
        resultsList.innerHTML = '';
        if (results.length === 0) {
            resultsList.innerHTML = '<li>未找到结果。</li>';
            return;
        }
        results.forEach(item => {
            const li = document.createElement('li');
            const infoDiv = document.createElement('div');
            infoDiv.className = 'info';
            
            const titleP = document.createElement('p');
            titleP.className = 'title';
            titleP.textContent = item.title;
            
            const metaP = document.createElement('p');
            metaP.className = 'meta';
            metaP.textContent = `源: ${item.provider} | 类型: ${item.type} | 年份: ${item.year || 'N/A'}`;
            
            infoDiv.appendChild(titleP);
            infoDiv.appendChild(metaP);

            const importBtn = document.createElement('button');
            importBtn.textContent = '导入弹幕';
            importBtn.addEventListener('click', async () => {
                importBtn.disabled = true;
                importBtn.textContent = '导入中...';
                log(`开始从 [${item.provider}] 导入 [${item.title}]...`);
                try {
                    const data = await apiFetch('/api/v2/import', {
                        method: 'POST',
                        body: JSON.stringify({
                            provider: item.provider,
                            media_id: item.mediaId,
                            anime_title: item.title,
                        }),
                    });
                    log(data.message);
                } catch (error) {
                    log(`导入失败: ${error.message}`);
                } finally {
                    importBtn.disabled = false;
                    importBtn.textContent = '导入弹幕';
                }
            });

            li.appendChild(infoDiv);
            li.appendChild(importBtn);
            resultsList.appendChild(li);
        });
    }

    changePasswordForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        passwordChangeMessage.textContent = '';
        passwordChangeMessage.className = 'message'; // Reset class

        const oldPassword = document.getElementById('old-password').value;
        const newPassword = document.getElementById('new-password').value;
        const confirmPassword = document.getElementById('confirm-password').value;

        if (newPassword.length < 8) {
            passwordChangeMessage.textContent = '新密码至少需要8位。';
            passwordChangeMessage.classList.add('error');
            return;
        }

        if (newPassword !== confirmPassword) {
            passwordChangeMessage.textContent = '两次输入的新密码不一致。';
            passwordChangeMessage.classList.add('error');
            return;
        }

        try {
            await apiFetch('/api/v2/auth/users/me/password', {
                method: 'PUT',
                body: JSON.stringify({
                    old_password: oldPassword,
                    new_password: newPassword,
                }),
            });
            passwordChangeMessage.textContent = '密码修改成功！';
            passwordChangeMessage.classList.add('success');
            log('密码已成功修改。');
            changePasswordForm.reset();
        } catch (error) {
            passwordChangeMessage.textContent = `修改失败: ${error.message}`;
            passwordChangeMessage.classList.add('error');
            log(`修改密码失败: ${error.message}`);
        }
    });

    // Initial check
    checkLogin();
});