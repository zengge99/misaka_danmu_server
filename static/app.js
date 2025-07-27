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
    const backToLibraryBtn = document.getElementById('back-to-library-btn');


    // Sources View Elements
    const sourcesList = document.getElementById('sources-list');
    const saveSourcesBtn = document.getElementById('save-sources-btn');
    const toggleSourceBtn = document.getElementById('toggle-source-btn');
    const moveSourceUpBtn = document.getElementById('move-source-up-btn');
    const moveSourceDownBtn = document.getElementById('move-source-down-btn');

    // --- State ---
    let token = localStorage.getItem('danmu_api_token');
    let logRefreshInterval = null; // For polling server logs

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
        
        if (response.status === 204) { // Handle No Content response
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
            startLogRefresh(); // Start polling for logs on successful login
        } catch (error) {
            console.error(`自动登录失败: ${error.message}`);
            logout();
        }
    }

    function logout() {
        token = null;
        localStorage.removeItem('danmu_api_token');
        showView('auth');
        stopLogRefresh(); // Stop polling for logs on logout
    }

    // --- Log Polling ---
    function startLogRefresh() {
        refreshServerLogs(); // Initial fetch
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
            // This will be caught by apiFetch which calls logout() on 401
            console.error("刷新日志失败:", error.message);
        }
    }

    // --- Event Listeners ---

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

    // Registration
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
            alert(`用户 '${username}' 注册成功，请登录。`);
            registerForm.reset();
            showLoginLink.click();
        } catch (error) {
            authError.textContent = `注册失败: ${error.message}`;
        }
    });

    // Login
    loginForm.addEventListener('submit', async (e) => {
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
    });

    // Sidebar Navigation
    sidebar.addEventListener('click', (e) => {
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
                // 确保详情页被隐藏
                libraryView.classList.remove('hidden');
                animeDetailView.classList.add('hidden');

            } else if (viewId === 'sources-view') {
                loadScraperSettings();
            }
        }
    });

    // Search
    searchForm.addEventListener('submit', async (e) => {
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
                            current_episode_index: item.currentEpisodeIndex, // 新增：将当前集数一同提交
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

    // Change Password
    changePasswordForm.addEventListener('submit', async (e) => {
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
    });

    // Library View
    async function loadLibrary() {
        if (!libraryTableBody) return;
        libraryTableBody.innerHTML = '<tr><td colspan="6">加载中...</td></tr>';
        try {
            const data = await apiFetch('/api/v2/library');
            renderLibrary(data.animes);
        } catch (error) {
            libraryTableBody.innerHTML = `<tr><td colspan="6" class="error">加载失败: ${error.message}</td></tr>`;
        }
    }

    function renderLibrary(animes) {
        libraryTableBody.innerHTML = '';
        if (animes.length === 0) {
            libraryTableBody.innerHTML = '<tr><td colspan="6">媒体库为空。</td></tr>';
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
            row.insertCell().textContent = new Date(anime.createdAt).toLocaleString();

            const actionsCell = row.insertCell();
            actionsCell.className = 'actions-cell';
            actionsCell.innerHTML = `
                <button class="action-btn" title="编辑" onclick="handleAction('edit', ${anime.animeId})">✏️</button>
                <button class="action-btn" title="全量刷新" onclick="handleAction('refresh_full', ${anime.animeId})">🔄</button>
                <button class="action-btn" title="增量刷新" onclick="handleAction('refresh_inc', ${anime.animeId})">➕</button>
                <button class="action-btn" title="定时刷新" onclick="handleAction('schedule', ${anime.animeId})">⏰</button>
                <button class="action-btn" title="查看剧集" onclick="handleAction('view', ${anime.animeId})">📖</button>
                <button class="action-btn" title="删除" onclick="handleAction('delete', ${anime.animeId})">🗑️</button>
            `;
        });
    }

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
            const currentSeason = row ? row.cells[2].textContent : '1';
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

        } else if (action === 'refresh_full') {
            if (confirm(`您确定要为 '${title}' 执行全量刷新吗？\n这将删除所有现有弹幕并从源重新获取。`)) {
                apiFetch(`/api/v2/library/anime/${animeId}/refresh`, {
                    method: 'POST',
                }).then(response => {
                    alert(response.message || "全量刷新任务已开始，请在日志中查看进度。");
                }).catch(error => {
                    alert(`启动刷新任务失败: ${error.message}`);
                });
            }
        } else {
            alert(`功能 '${action}' 尚未实现。`);
        }
    };

    backToLibraryBtn.addEventListener('click', () => {
        animeDetailView.classList.add('hidden');
        libraryView.classList.remove('hidden');
    });

    // --- Scraper Sources View ---
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

    toggleSourceBtn.addEventListener('click', () => {
        const selected = sourcesList.querySelector('li.selected');
        if (!selected) return;
        const isEnabled = selected.dataset.isEnabled === 'true';
        selected.dataset.isEnabled = !isEnabled;
        selected.querySelector('.status-icon').textContent = !isEnabled ? '✅' : '❌';
    });

    moveSourceUpBtn.addEventListener('click', () => {
        const selected = sourcesList.querySelector('li.selected');
        if (selected && selected.previousElementSibling) {
            sourcesList.insertBefore(selected, selected.previousElementSibling);
        }
    });

    moveSourceDownBtn.addEventListener('click', () => {
        const selected = sourcesList.querySelector('li.selected');
        if (selected && selected.nextElementSibling) {
            sourcesList.insertBefore(selected.nextElementSibling, selected);
        }
    });

    saveSourcesBtn.addEventListener('click', async () => {
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
            // 重新加载以确认顺序
            loadScraperSettings();
        } catch (error) {
            alert(`保存失败: ${error.message}`);
        } finally {
            saveSourcesBtn.disabled = false;
            saveSourcesBtn.textContent = '保存设置';
        }
    });

    // --- Anime Detail View ---
    async function showAnimeDetail(animeId) {
        libraryView.classList.add('hidden');
        animeDetailView.classList.remove('hidden');
        animeDetailView.innerHTML = '<button id="back-to-library-btn"> &lt; 返回弹幕库</button><div>加载中...</div>';
        // Re-bind the back button event since we just overwrote the innerHTML
        document.getElementById('back-to-library-btn').addEventListener('click', () => {
            animeDetailView.classList.add('hidden');
            libraryView.classList.remove('hidden');
        });

        try {
            // NOTE: We need a new API endpoint to get sources for a specific anime
            // For now, we'll filter from the full library list as a workaround.
            // A real implementation would be: const sources = await apiFetch(`/api/v2/library/anime/${animeId}/sources`);
            const fullLibrary = await apiFetch('/api/v2/library');
            const anime = fullLibrary.animes.find(a => a.animeId === animeId);
            
            // This is a placeholder. A real implementation requires a dedicated API endpoint.
            // Let's assume a new endpoint `/api/v2/library/anime/{animeId}/sources` exists
            // and it returns a list of sources.
            // For this example, we'll just show a message.
            renderAnimeDetailView(anime, []); // Pass empty sources for now

        } catch (error) {
            animeDetailView.innerHTML += `<div class="error">加载详情失败: ${error.message}</div>`;
        }
    }

    function renderAnimeDetailView(anime, sources) {
        // This is a mock-up of what the detail view would look like.
        // A full implementation requires backend changes to support getting sources per anime.
        let html = `
            <button id="back-to-library-btn"> &lt; 返回弹幕库</button>
            <div class="anime-detail-header">
                <img src="${anime.imageUrl || '/static/placeholder.png'}" alt="${anime.title}">
                <div>
                    <h2>${anime.title}</h2>
                    <p>季: ${anime.season} | 总集数: ${anime.episodeCount}</p>
                </div>
            </div>
            <h3>关联的数据源</h3>
            <table id="source-detail-table">
                <thead>
                    <tr>
                        <th>数据源</th>
                        <th>源ID</th>
                        <th>收录时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    <!-- This part would be populated by a new API call -->
                    <tr><td colspan="4">功能待实现：此处将显示 '${anime.title}' 的所有弹幕源。</td></tr>
                </tbody>
            </table>
        `;
        animeDetailView.innerHTML = html;
        document.getElementById('back-to-library-btn').addEventListener('click', () => {
            animeDetailView.classList.add('hidden');
            libraryView.classList.remove('hidden');
        });
    }


    // Logout
    logoutBtn.addEventListener('click', logout);

    // --- Initial Load ---
    checkLogin();
});
