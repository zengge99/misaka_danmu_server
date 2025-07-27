document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const authView = document.getElementById('auth-view');
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const showRegisterLink = document.getElementById('show-register-link');
    const showLoginLink = document.getElementById('show-login-link');
    const authError = document.getElementById('auth-error');

    const mainView = document.getElementById('main-view');
    const currentUserSpan = document.getElementById('current-user');
    const logoutBtn = document.getElementById('logout-btn');
    
    const sidebar = document.getElementById('sidebar');
    const contentViews = document.querySelectorAll('.content-view');

    const searchForm = document.getElementById('search-form');
    const searchKeywordInput = document.getElementById('search-keyword');
    const resultsList = document.getElementById('results-list');
    const logOutput = document.getElementById('log-output');
    const loader = document.getElementById('loader');
    
    const changePasswordForm = document.getElementById('change-password-form');
    const passwordChangeMessage = document.getElementById('password-change-message');

    const libraryTableBody = document.querySelector('#library-table tbody');
    const libraryView = document.getElementById('library-view');
    const animeDetailView = document.getElementById('anime-detail-view');

    // Sources View Elements
    const sourcesList = document.getElementById('sources-list');
    const saveSourcesBtn = document.getElementById('save-sources-btn');
    const toggleSourceBtn = document.getElementById('toggle-source-btn');
    const moveSourceUpBtn = document.getElementById('move-source-up-btn');
    const moveSourceDownBtn = document.getElementById('move-source-down-btn');

    // --- State ---
    let token = localStorage.getItem('danmu_api_token');
    let logRefreshInterval = null;

    // --- Core Functions ---
    function toggleLoader(show) {
        if (!loader) return;
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

        if (response.status === 401) {
            logout();
            throw new Error("会话已过期或无效，请重新登录。");
        }

        if (!response.ok) {
            let errorMessage = `HTTP error! status: ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.detail || JSON.stringify(errorData);
            } catch (e) {
                errorMessage = await response.text().catch(() => errorMessage);
            }
            throw new Error(errorMessage);
        }
        
        if (response.status === 204) {
            return {};
        }
        
        const responseText = await response.text();
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
            if (!user || !user.username) {
                throw new Error('未能获取到有效的用户信息。');
            }
            currentUserSpan.textContent = `用户: ${user.username}`;
            showView('main');
            startLogRefresh();
        } catch (error) {
            console.error(`自动登录失败: ${error.message}`);
            logout();
        }
    }

    function logout() {
        token = null;
        localStorage.removeItem('danmu_api_token');
        showView('auth');
        stopLogRefresh();
    }

    // --- Log Polling ---
    function startLogRefresh() {
        refreshServerLogs();
        if (logRefreshInterval) clearInterval(logRefreshInterval);
        logRefreshInterval = setInterval(refreshServerLogs, 3000);
    }

    function stopLogRefresh() {
        if (logRefreshInterval) clearInterval(logRefreshInterval);
        logRefreshInterval = null;
    }

    async function refreshServerLogs() {
        if (!token || !logOutput) return;
        try {
            const logs = await apiFetch('/api/v2/logs');
            logOutput.textContent = logs.join('\n');
        } catch (error) {
            console.error("刷新日志失败:", error.message);
        }
    }

    // --- Event Listeners Setup ---
    function setupEventListeners() {
        // Auth Form Switching
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

        // Forms
        registerForm.addEventListener('submit', handleRegister);
        loginForm.addEventListener('submit', handleLogin);
        searchForm.addEventListener('submit', handleSearch);
        changePasswordForm.addEventListener('submit', handleChangePassword);

        // Sidebar Navigation
        sidebar.addEventListener('click', handleSidebarNavigation);

        // Buttons
        logoutBtn.addEventListener('click', logout);
        saveSourcesBtn.addEventListener('click', handleSaveSources);
        toggleSourceBtn.addEventListener('click', handleToggleSource);
        moveSourceUpBtn.addEventListener('click', handleMoveSourceUp);
        moveSourceDownBtn.addEventListener('click', handleMoveSourceDown);
    }

    // --- Event Handlers ---

    async function handleRegister(e) {
        e.preventDefault();
        authError.textContent = '';
        const username = document.getElementById('register-username').value;
        const password = document.getElementById('register-password').value;

        try {
            await apiFetch('/api/v2/auth/register', {
                method: 'POST',
                body: JSON.stringify({ username, password }),
            });
            alert(`用户 '${username}' 注册成功，请登录。`);
            registerForm.reset();
            showLoginLink.click();
        } catch (error) {
            authError.textContent = `注册失败: ${error.message}`;
        }
    }

    async function handleLogin(e) {
        e.preventDefault();
        authError.textContent = '';
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;

        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        try {
            const response = await fetch('/api/v2/auth/token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData,
            });

            if (!response.ok) {
                let errorDetail = '用户名或密码错误';
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch (jsonError) { /* ignore */ }
                throw new Error(errorDetail);
            }

            const data = await response.json();
            token = data.access_token;
            localStorage.setItem('danmu_api_token', token);
            loginForm.reset();
            await checkLogin();
        } catch (error) {
            authError.textContent = `登录失败: ${error.message}`;
        }
    }

    function handleSidebarNavigation(e) {
        const navLink = e.target.closest('.nav-link');
        if (navLink) {
            e.preventDefault();
            const viewId = navLink.getAttribute('data-view');
            if (!viewId) return;

            sidebar.querySelectorAll('.nav-link').forEach(link => link.classList.remove('active'));
            navLink.classList.add('active');

            contentViews.forEach(view => view.classList.add('hidden'));
            const targetView = document.getElementById(viewId);
            if (targetView) {
                targetView.classList.remove('hidden');
            }

            if (viewId === 'library-view') {
                loadLibrary();
            } else if (viewId === 'sources-view') {
                loadScraperSettings();
            }
        }
    }

    async function handleSearch(e) {
        e.preventDefault();
        const keyword = searchKeywordInput.value;
        if (!keyword) return;

        resultsList.innerHTML = '';
        toggleLoader(true);

        try {
            const data = await apiFetch(`/api/v2/search/provider?keyword=${encodeURIComponent(keyword)}`);
            displayResults(data.results);
        } catch (error) {
            alert(`搜索失败: ${error.message}`);
        } finally {
            toggleLoader(false);
        }
    }

    async function handleChangePassword(e) {
        e.preventDefault();
        passwordChangeMessage.textContent = '';
        passwordChangeMessage.className = 'message';

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
            changePasswordForm.reset();
        } catch (error) {
            passwordChangeMessage.textContent = `修改失败: ${error.message}`;
            passwordChangeMessage.classList.add('error');
        }
    }

    function handleToggleSource() {
        const selected = sourcesList.querySelector('li.selected');
        if (!selected) return;
        const isEnabled = selected.dataset.isEnabled === 'true';
        selected.dataset.isEnabled = !isEnabled;
        selected.querySelector('.status-icon').textContent = !isEnabled ? '✅' : '❌';
    }

    function handleMoveSourceUp() {
        const selected = sourcesList.querySelector('li.selected');
        if (selected && selected.previousElementSibling) {
            sourcesList.insertBefore(selected, selected.previousElementSibling);
        }
    }

    function handleMoveSourceDown() {
        const selected = sourcesList.querySelector('li.selected');
        if (selected && selected.nextElementSibling) {
            sourcesList.insertBefore(selected.nextElementSibling, selected);
        }
    }

    async function handleSaveSources() {
        const settingsToSave = [];
        sourcesList.querySelectorAll('li').forEach((li, index) => {
            settingsToSave.push({
                provider_name: li.dataset.providerName,
                is_enabled: li.dataset.isEnabled === 'true',
                display_order: index + 1,
            });
        });

        try {
            saveSourcesBtn.disabled = true;
            saveSourcesBtn.textContent = '保存中...';
            await apiFetch('/api/v2/scrapers', {
                method: 'PUT',
                body: JSON.stringify(settingsToSave),
            });
            alert('搜索源设置已保存！');
            loadScraperSettings();
        } catch (error) {
            alert(`保存失败: ${error.message}`);
        } finally {
            saveSourcesBtn.disabled = false;
            saveSourcesBtn.textContent = '保存设置';
        }
    }

    // --- Rendering Functions ---

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
            let metaText = `源: ${item.provider} | 类型: ${item.type} | 年份: ${item.year || 'N/A'}`;
            if (item.type === 'tv_series' && item.episodeCount) {
                metaText += ` | 总集数: ${item.episodeCount}`;
            }
            if (item.currentEpisodeIndex) {
                metaText += ` | 当前集: ${item.currentEpisodeIndex}`;
            }
            metaP.textContent = metaText;
            
            infoDiv.appendChild(titleP);
            infoDiv.appendChild(metaP);

            const importBtn = document.createElement('button');
            importBtn.textContent = '导入弹幕';
            importBtn.addEventListener('click', async () => {
                importBtn.disabled = true;
                importBtn.textContent = '导入中...';
                try {
                    const data = await apiFetch('/api/v2/import', {
                        method: 'POST',
                        body: JSON.stringify({
                            provider: item.provider,
                            media_id: item.mediaId,
                            anime_title: item.title,
                            type: item.type,
                            current_episode_index: item.currentEpisodeIndex,
                        }),
                    });
                    alert(data.message);
                } catch (error) {
                    alert(`提交导入任务失败: ${error.message}`);
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

    async function loadLibrary() {
        if (!libraryTableBody) return;
        libraryTableBody.innerHTML = '<tr><td colspan="7">加载中...</td></tr>';
        try {
            const data = await apiFetch('/api/v2/library');
            renderLibrary(data.animes);
        } catch (error) {
            libraryTableBody.innerHTML = `<tr><td colspan="7" class="error">加载失败: ${error.message}</td></tr>`;
        }
    }

    function renderLibrary(animes) {
        libraryTableBody.innerHTML = '';
        if (animes.length === 0) {
            libraryTableBody.innerHTML = '<tr><td colspan="7">媒体库为空。</td></tr>';
            return;
        }

        animes.forEach(anime => {
            const row = libraryTableBody.insertRow();
            
            const posterCell = row.insertCell();
            posterCell.className = 'poster-cell';
            const img = document.createElement('img');
            img.src = anime.imageUrl || '/static/placeholder.png';
            img.alt = anime.title;
            posterCell.appendChild(img);

            row.insertCell().textContent = anime.title;
            row.insertCell().textContent = anime.season;
            row.insertCell().textContent = anime.episodeCount;
            row.insertCell().textContent = anime.sourceCount;
            row.insertCell().textContent = new Date(anime.createdAt).toLocaleString();

            const actionsCell = row.insertCell();
            actionsCell.className = 'actions-cell';
            actionsCell.innerHTML = `
                <button class="action-btn" title="编辑" onclick="handleAction('edit', ${anime.animeId})">✏️</button>
                <button class="action-btn" title="查看数据源" onclick="handleAction('view', ${anime.animeId})">📖</button>
                <button class="action-btn" title="删除" onclick="handleAction('delete', ${anime.animeId})">🗑️</button>
            `;
        });
    }

    async function loadScraperSettings() {
        if (!sourcesList) return;
        sourcesList.innerHTML = '<li>加载中...</li>';
        try {
            const settings = await apiFetch('/api/v2/scrapers');
            renderScraperSettings(settings);
        } catch (error) {
            sourcesList.innerHTML = `<li class="error">加载失败: ${error.message}</li>`;
        }
    }

    function renderScraperSettings(settings) {
        sourcesList.innerHTML = '';
        settings.forEach(setting => {
            const li = document.createElement('li');
            li.dataset.providerName = setting.provider_name;
            li.dataset.isEnabled = setting.is_enabled;
            li.textContent = setting.provider_name;

            const statusIcon = document.createElement('span');
            statusIcon.className = 'status-icon';
            statusIcon.textContent = setting.is_enabled ? '✅' : '❌';
            li.appendChild(statusIcon);

            li.addEventListener('click', () => {
                sourcesList.querySelectorAll('li').forEach(item => item.classList.remove('selected'));
                li.classList.add('selected');
            });
            sourcesList.appendChild(li);
        });
    }

    async function showAnimeDetailView(animeId) {
        libraryView.classList.add('hidden');
        animeDetailView.classList.remove('hidden');
        animeDetailView.innerHTML = '<div>加载中...</div>';

        try {
            const fullLibrary = await apiFetch('/api/v2/library');
            const anime = fullLibrary.animes.find(a => a.animeId === animeId);
            if (!anime) throw new Error("找不到该作品的信息。");

            const sources = await apiFetch(`/api/v2/library/anime/${animeId}/sources`);
            
            renderAnimeDetailView(anime, sources);

        } catch (error) {
            animeDetailView.innerHTML = `<div class="error">加载详情失败: ${error.message}</div>`;
        }
    }

    function renderAnimeDetailView(anime, sources) {
        let html = `
            <button id="back-to-library-btn"> &lt; 返回弹幕库</button>
            <div class="anime-detail-header">
                <img src="${anime.imageUrl || '/static/placeholder.png'}" alt="${anime.title}">
                <div>
                    <h2>${anime.title}</h2>
                    <p>季: ${anime.season} | 总集数: ${anime.episodeCount || 0} | 已关联 ${sources.length} 个源</p>
                </div>
            </div>
            <h3>关联的数据源</h3>
            <table id="source-detail-table">
                <thead>
                    <tr>
                        <th>源提供方</th>
                        <th>源媒体ID</th>
                        <th>收录时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                </tbody>
            </table>
        `;
        animeDetailView.innerHTML = html;

        const sourceTableBody = animeDetailView.querySelector('#source-detail-table tbody');
        if (sources.length > 0) {
            sources.forEach(source => {
                const row = sourceTableBody.insertRow();
                row.insertCell().textContent = source.provider_name;
                row.insertCell().textContent = source.media_id;
                row.insertCell().textContent = new Date(source.created_at).toLocaleString();
                const actionsCell = row.insertCell();
                actionsCell.innerHTML = `
                    <button class="action-btn" title="刷新此源" onclick="handleSourceAction('refresh', ${source.source_id}, '${anime.title}')">🔄</button>
                    <button class="action-btn" title="删除此源" onclick="handleSourceAction('delete', ${source.source_id}, '${anime.title}')">🗑️</button>
                `;
            });
        } else {
            sourceTableBody.innerHTML = `<tr><td colspan="4">未关联任何数据源。</td></tr>`;
        }

        document.getElementById('back-to-library-btn').addEventListener('click', () => {
            animeDetailView.classList.add('hidden');
            libraryView.classList.remove('hidden');
        });
    }

    function refreshSource(sourceId, title) {
        if (confirm(`您确定要为 '${title}' 的这个数据源执行全量刷新吗？`)) {
            apiFetch(`/api/v2/library/source/${sourceId}/refresh`, {
                method: 'POST',
            }).then(response => {
                alert(response.message || "刷新任务已开始，请在日志中查看进度。");
            }).catch(error => {
                alert(`启动刷新任务失败: ${error.message}`);
            });
        }
    }

    // --- Global Action Handlers ---
    window.handleAction = (action, animeId) => {
        const row = document.querySelector(`#library-table button[onclick*="handleAction('${action}', ${animeId})"]`).closest('tr');
        const title = row ? row.cells[1].textContent : `ID: ${animeId}`;

        if (action === 'delete') {
            if (confirm(`您确定要删除番剧 '${title}' 吗？\n此操作将删除其所有分集和弹幕，且不可恢复。`)) {
                apiFetch(`/api/v2/library/anime/${animeId}`, {
                    method: 'DELETE',
                }).then(() => {
                    loadLibrary();
                }).catch(error => {
                    alert(`删除失败: ${error.message}`);
                });
            }
        } else if (action === 'edit') {
            const currentSeason = row ? parseInt(row.cells[2].textContent, 10) : 1;
            const newTitle = prompt("请输入新的影视名称：", title);
            if (newTitle === null) return;
            const newSeasonStr = prompt("请输入新的季数：", currentSeason);
            if (newSeasonStr === null) return;

            const newSeason = parseInt(newSeasonStr, 10);
            if (isNaN(newSeason) || newSeason < 1) {
                alert("季数必须是一个大于0的数字。");
                return;
            }

            apiFetch(`/api/v2/library/anime/${animeId}`, {
                method: 'PUT',
                body: JSON.stringify({ title: newTitle, season: newSeason }),
            }).then(() => {
                alert("信息更新成功！");
                loadLibrary();
            }).catch(error => {
                alert(`更新失败: ${error.message}`);
            });
        } else if (action === 'view') {
            showAnimeDetailView(animeId);
        } else {
            alert(`功能 '${action}' 尚未实现。`);
        }
    };

    window.handleSourceAction = (action, sourceId, title) => {
        if (action === 'refresh') {
            refreshSource(sourceId, title);
        } else if (action === 'delete') {
            // Placeholder for deleting a source
            alert(`功能 '删除源' (ID: ${sourceId}) 尚未实现。`);
        }
    };

    // --- Initial Load ---
    setupEventListeners();
    checkLogin();
});
