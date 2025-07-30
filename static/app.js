document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const authView = document.getElementById('auth-view');
    const loginForm = document.getElementById('login-form');
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
    const editAnimeView = document.getElementById('edit-anime-view');
    const episodeListView = document.getElementById('episode-list-view');
    const danmakuListView = document.getElementById('danmaku-list-view');
    const editEpisodeView = document.getElementById('edit-episode-view');
    const editEpisodeForm = document.getElementById('edit-episode-form');
    const editAnimeForm = document.getElementById('edit-anime-form');
    const librarySearchInput = document.getElementById('library-search-input');

    // Sources View Elements
    const sourcesList = document.getElementById('sources-list');
    const saveSourcesBtn = document.getElementById('save-sources-btn');
    const toggleSourceBtn = document.getElementById('toggle-source-btn');
    const moveSourceUpBtn = document.getElementById('move-source-up-btn');
    const moveSourceDownBtn = document.getElementById('move-source-down-btn');

    const taskManagerView = document.getElementById('task-manager-view');
    const taskListUl = document.getElementById('task-list');

    const tokenManagerView = document.getElementById('token-manager-view');
    const tokenTableBody = document.querySelector('#token-table tbody');
    const addTokenBtn = document.getElementById('add-token-btn');
    const addTokenView = document.getElementById('add-token-view');
    const addTokenForm = document.getElementById('add-token-form');
    const customDomainInput = document.getElementById('custom-domain-input');
    const saveDomainBtn = document.getElementById('save-domain-btn');
    const domainSaveMessage = document.getElementById('domain-save-message');

    // --- State ---
    let token = localStorage.getItem('danmu_api_token');
    let logRefreshInterval = null;
    let clearedTaskIds = new Set(); // 新增：用于存储已从视图中清除的任务ID

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
            const user = await apiFetch('/api/ui/auth/users/me');
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
        loadAndRenderTasks(); // Also load tasks initially
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
            const logs = await apiFetch('/api/ui/logs');
            logOutput.textContent = logs.join('\n');
        } catch (error) {
            console.error("刷新日志失败:", error.message);
        }
    }

    // --- Task Polling ---
    async function loadAndRenderTasks() {
        if (!token || taskManagerView.classList.contains('hidden')) return;
        try {
            const tasks = await apiFetch('/api/ui/tasks');
            renderTasks(tasks);
        } catch (error) {
            console.error("刷新日志失败:", error.message);
        }
    }

    // --- Event Listeners Setup ---
    function setupEventListeners() {
        // ... (其他监听器保持不变)

        // Forms
        loginForm.addEventListener('submit', handleLogin);
        searchForm.addEventListener('submit', handleSearch);
        changePasswordForm.addEventListener('submit', handleChangePassword);
        editAnimeForm.addEventListener('submit', handleEditAnimeSave);
        editEpisodeForm.addEventListener('submit', handleEditEpisodeSave);

        // Sidebar Navigation
        sidebar.addEventListener('click', handleSidebarNavigation);

        // Buttons
        logoutBtn.addEventListener('click', logout);
        saveSourcesBtn.addEventListener('click', handleSaveSources);
        saveDomainBtn.addEventListener('click', handleSaveDomain);
        toggleSourceBtn.addEventListener('click', handleToggleSource);
        moveSourceUpBtn.addEventListener('click', handleMoveSourceUp);
        moveSourceDownBtn.addEventListener('click', handleMoveSourceDown);
        addTokenBtn.addEventListener('click', () => {
            tokenManagerView.classList.add('hidden');
            addTokenView.classList.remove('hidden');
            addTokenForm.reset(); // 每次显示时清空表单
        });
        document.getElementById('back-to-library-from-edit-btn').addEventListener('click', () => {
            editAnimeView.classList.add('hidden');
            libraryView.classList.remove('hidden');
        });
        document.getElementById('back-to-tokens-from-add-btn').addEventListener('click', () => {
            addTokenView.classList.add('hidden');
            tokenManagerView.classList.remove('hidden');
        });
        document.getElementById('back-to-episodes-from-edit-btn').addEventListener('click', () => {
            editEpisodeView.classList.add('hidden');
            // Retrieve context to navigate back
            const sourceId = parseInt(document.getElementById('edit-episode-source-id').value, 10);
            const animeTitle = document.getElementById('edit-episode-anime-title').value;
             const animeId = parseInt(document.getElementById('edit-episode-anime-id').value, 10);
            showEpisodeListView(sourceId, animeTitle,animeId);
        });

        addTokenForm.addEventListener('submit', handleAddTokenSave);
        // Inputs
        librarySearchInput.addEventListener('input', handleLibrarySearch);
    }

    // --- Event Handlers ---

    async function handleLogin(e) {
        e.preventDefault();
        authError.textContent = '';
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;

        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        try {
            const response = await fetch('/api/ui/auth/token', {
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
            authError.textContent = `登录失败: ${(error.message || error)}`;
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
            } else if (viewId === 'task-manager-view') {
                loadAndRenderTasks(); // Load immediately on view switch
            } else if (viewId === 'token-manager-view') {
                loadAndRenderTokens();
                loadCustomDomain();
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
            const data = await apiFetch(`/api/ui/search/provider?keyword=${encodeURIComponent(keyword)}`);
            displayResults(data.results);
        } catch (error) {
            alert(`搜索失败: ${(error.message || error)}`);
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
            await apiFetch('/api/ui/auth/users/me/password', {
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
            passwordChangeMessage.textContent = `修改失败: ${(error.message || error)}`;
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
            await apiFetch('/api/ui/scrapers', {
                method: 'PUT',
                body: JSON.stringify(settingsToSave),
            });
            alert('搜索源设置已保存！');
            loadScraperSettings();
        } catch (error) {
            alert(`保存失败: ${(error.message || error)}`);
        } finally {
            saveSourcesBtn.disabled = false;
            saveSourcesBtn.textContent = '保存设置';
        }
    }

    function handleLibrarySearch() {
        const searchTerm = librarySearchInput.value.toLowerCase();
        const rows = libraryTableBody.querySelectorAll('tr');
        rows.forEach(row => {
            const titleCell = row.cells[1];
            if (titleCell) {
                const title = titleCell.textContent.toLowerCase();
                row.style.display = title.includes(searchTerm) ? '' : 'none';
            }
        });
    }

    async function handleEditAnimeSave(e) {
        e.preventDefault();
        const animeId = document.getElementById('edit-anime-id').value;
        const newTitle = document.getElementById('edit-anime-title').value;
        const newSeason = parseInt(document.getElementById('edit-anime-season').value, 10);

        if (isNaN(newSeason) || newSeason < 1) {
            alert("季数必须是一个大于0的数字。");
            return;
        }

        const saveButton = editAnimeForm.querySelector('button[type="submit"]');
        saveButton.disabled = true;
        saveButton.textContent = '保存中...';

        try {
            await apiFetch(`/api/ui/library/anime/${animeId}`, {
                method: 'PUT',
                body: JSON.stringify({ title: newTitle, season: newSeason }),
            });
            alert("信息更新成功！");
            document.getElementById('back-to-library-from-edit-btn').click();
            loadLibrary();
        } catch (error) {
            alert(`更新失败: ${(error.message || error)}`);
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = '保存更改';
        }
    }

    async function handleEditEpisodeSave(e) {
        e.preventDefault();
        const episodeId = document.getElementById('edit-episode-id').value;
        const newTitle = document.getElementById('edit-episode-title').value;
        const newIndex = parseInt(document.getElementById('edit-episode-index').value, 10);
        const newUrl = document.getElementById('edit-episode-url').value;

        if (isNaN(newIndex) || newIndex < 1) {
            alert("集数必须是一个大于0的数字。");
            return;
        }

        const saveButton = editEpisodeForm.querySelector('button[type="submit"]');
        saveButton.disabled = true;
        saveButton.textContent = '保存中...';

        try {
            await apiFetch(`/api/ui/library/episode/${episodeId}`, {
                method: 'PUT',
                body: JSON.stringify({
                    title: newTitle,
                    episode_index: newIndex,
                    source_url: newUrl
                })
            });
            alert("分集信息更新成功！");
            document.getElementById('back-to-episodes-from-edit-btn').click();
        } catch (error) {
            alert(`更新失败: ${(error.message || error)}`);
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = '保存更改';
        }
    }

    async function handleAddTokenSave(e) {
        e.preventDefault();
        const nameInput = document.getElementById('add-token-name');
        const name = nameInput.value.trim();
        if (!name) {
            alert('名称不能为空。');
            return;
        }

        const saveButton = addTokenForm.querySelector('button[type="submit"]');
        saveButton.disabled = true;
        saveButton.textContent = '保存中...';

        try {
            await apiFetch('/api/ui/tokens', {
                method: 'POST',
                body: JSON.stringify({ name: name }),
            });
            // 成功后，自动点击返回按钮并刷新列表
            document.getElementById('back-to-tokens-from-add-btn').click();
            loadAndRenderTokens();
        } catch (error) {
            alert(`添加失败: ${(error.message || error)}`);
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = '保存';
        }
    }

    async function handleSaveDomain() {
        const domain = customDomainInput.value.trim();
        // 自动移除末尾的斜杠，以规范格式
        const cleanedDomain = domain.endsWith('/') ? domain.slice(0, -1) : domain;
        
        domainSaveMessage.textContent = '';
        domainSaveMessage.className = 'message';
        saveDomainBtn.disabled = true;
        saveDomainBtn.textContent = '保存中...';

        try {
            await apiFetch('/api/ui/config/custom_api_domain', {
                method: 'PUT',
                body: JSON.stringify({ value: cleanedDomain })
            });
            domainSaveMessage.textContent = '域名保存成功！';
            domainSaveMessage.classList.add('success');
            customDomainInput.value = cleanedDomain; // 更新输入框为清理后的值
        } catch (error) {
            domainSaveMessage.textContent = `保存失败: ${(error.message || error)}`;
            domainSaveMessage.classList.add('error');
        } finally {
            saveDomainBtn.disabled = false;
            saveDomainBtn.textContent = '保存域名';
        }
    }
    // --- Task Manager View (Optimized Rendering) ---
    function renderTasks(tasks) {
        if (!taskListUl) return;

        // 过滤掉那些已经被前端清除的任务
        const tasksToRender = tasks.filter(task => !clearedTaskIds.has(task.task_id));

        // If no tasks, show message and clear list
        if (tasksToRender.length === 0) {
            taskListUl.innerHTML = '<li>当前没有任务。</li>';
            return;
        }

        // 如果列表之前显示的是“没有任务”的消息，则先清空它
        const noTasksLi = taskListUl.querySelector('li:not(.task-item)');
        if (noTasksLi) {
            taskListUl.innerHTML = '';
        }

        const existingTaskElements = new Map([...taskListUl.querySelectorAll('.task-item')].map(el => [el.dataset.taskId, el]));
        const incomingTaskIds = new Set(tasksToRender.map(t => t.task_id));

        // Remove tasks that are no longer in the list (e.g., if backend state is cleared)
        for (const [taskId, element] of existingTaskElements.entries()) {
            if (!incomingTaskIds.has(taskId)) {
                element.remove();
            }
        }

        // Update existing or add new tasks
        tasksToRender.forEach(task => {
            const statusColor = {
                "已完成": "var(--success-color)",
                "失败": "var(--error-color)",
                "排队中": "#909399",
                "运行中": "var(--primary-color)"
            }[task.status] || "var(--primary-color)";

            let taskElement = existingTaskElements.get(task.task_id);

            if (taskElement) {
                // Update existing element
                if (taskElement.dataset.status !== task.status) {
                    taskElement.dataset.status = task.status;
                    taskElement.querySelector('.task-status').textContent = task.status;
                }
                taskElement.querySelector('.task-description').textContent = task.description;
                taskElement.querySelector('.task-progress-bar').style.width = `${task.progress}%`;
                taskElement.querySelector('.task-progress-bar').style.backgroundColor = statusColor;
            } else {
                // Create new element
                const li = document.createElement('li');
                li.className = 'task-item';
                li.dataset.taskId = task.task_id;
                li.dataset.status = task.status;

                li.innerHTML = `
                    <div class="task-header">
                        <span class="task-title">${task.title}</span>
                        <span class="task-status">${task.status}</span>
                    </div>
                    <p class="task-description">${task.description}</p>
                    <div class="task-progress-bar-container">
                        <div class="task-progress-bar" style="width: ${task.progress}%; background-color: ${statusColor};"></div>
                    </div>
                `;
                taskListUl.appendChild(li);
                taskElement = li; // Use the newly created element for the next step
            }

            // Schedule removal for completed tasks
            if (task.status === '已完成' && !taskElement.dataset.removing) {
                taskElement.dataset.removing = 'true';
                // 立即将任务ID添加到已清除集合，防止下次轮询时再次渲染
                clearedTaskIds.add(task.task_id);

                setTimeout(() => {
                    taskElement.style.opacity = '0';
                    setTimeout(() => {
                        taskElement.remove();
                        // After removing, check if the list is now empty.
                        if (taskListUl.children.length === 0) {
                             taskListUl.innerHTML = '<li>当前没有任务。</li>';
                        }
                    }, 500); // This duration should match the CSS transition
                }, 2500); // Wait 2.5 seconds before starting the fade-out
            }
        });
    }

    // Start polling tasks when the app is loaded and user is logged in
    setInterval(loadAndRenderTasks, 800);

    // --- Rendering Functions ---

    function displayResults(results) {
        resultsList.innerHTML = '';
        if (results.length === 0) {
            resultsList.innerHTML = '<li>未找到结果。</li>';
            return;
        }
        results.forEach(item => {
            const li = document.createElement('li');

            const posterImg = document.createElement('img');
            posterImg.className = 'poster';
            posterImg.src = item.imageUrl || '/static/placeholder.png';
            posterImg.referrerPolicy = 'no-referrer'; // 关键修复：禁止发送Referer头
            posterImg.alt = item.title;
            li.appendChild(posterImg);

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
                    const data = await apiFetch('/api/ui/import', {
                        method: 'POST',
                        body: JSON.stringify({
                            provider: item.provider,
                            media_id: item.mediaId,
                            anime_title: item.title,
                            type: item.type,
                            image_url: item.imageUrl,
                            current_episode_index: item.currentEpisodeIndex,
                        }),
                    });
                    alert(data.message);
                } catch (error) {
                    alert(`提交导入任务失败: ${(error.message || error)}`);
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
            const data = await apiFetch('/api/ui/library');
            renderLibrary(data.animes);
        } catch (error) {
            libraryTableBody.innerHTML = `<tr><td colspan="7" class="error">加载失败: ${(error.message || error)}</td></tr>`;
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
            img.referrerPolicy = 'no-referrer'; // 关键修复：禁止发送Referer头
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
                <div class="action-buttons-wrapper">
                    <button class="action-btn" title="编辑" onclick="handleAction('edit', ${anime.animeId})">✏️</button>
                    <button class="action-btn" title="查看数据源" onclick="handleAction('view', ${anime.animeId})">📖</button>
                    <button class="action-btn" title="删除" onclick="handleAction('delete', ${anime.animeId})">🗑️</button>
                </div>
            `;
        });
    }

    async function loadScraperSettings() {
        if (!sourcesList) return;
        sourcesList.innerHTML = '<li>加载中...</li>';
        try {
            const settings = await apiFetch('/api/ui/scrapers');
            renderScraperSettings(settings);
        } catch (error) {
            sourcesList.innerHTML = `<li class="error">加载失败: ${(error.message || error)}</li>`;
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
        editAnimeView.classList.add('hidden');
        episodeListView.classList.add('hidden');
        danmakuListView.classList.add('hidden');
        animeDetailView.classList.remove('hidden');
        animeDetailView.innerHTML = '<div>加载中...</div>';

        try {
            const fullLibrary = await apiFetch('/api/ui/library');
            const anime = fullLibrary.animes.find(a => a.animeId === animeId);
            if (!anime) throw new Error("找不到该作品的信息。");

            const sources = await apiFetch(`/api/ui/library/anime/${animeId}/sources`);
            
            renderAnimeDetailView(anime, sources);

        } catch (error) {
            animeDetailView.innerHTML = `<div class="error">加载详情失败: ${(error.message || error)}</div>`;
        }
    }

    function renderAnimeDetailView(anime, sources) {
        let html = `
            <div class="view-header-flexible">
                <div class="anime-detail-header-main">
                    <img src="${anime.imageUrl || '/static/placeholder.png'}" alt="${anime.title}" referrerpolicy="no-referrer">
                    <div>
                        <h2>${anime.title}</h2>
                        <p>季: ${anime.season} | 总集数: ${anime.episodeCount || 0} | 已关联 ${sources.length} 个源</p>
                    </div>
                </div>
                <button id="back-to-library-btn"> &lt; 返回弹幕库</button>
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
                actionsCell.className = 'actions-cell';
                actionsCell.innerHTML = `
                    <div class="action-buttons-wrapper">
                        <button class="action-btn" title="精确标记" onclick="handleSourceAction('favorite', ${source.source_id}, '${anime.title.replace(/'/g, "\\'")}', ${anime.animeId})">${source.is_favorited ? '🌟' : '⭐'}</button>
                        <button class="action-btn" title="查看/编辑分集" onclick="handleSourceAction('view_episodes', ${source.source_id}, '${anime.title.replace(/'/g, "\\'")}', ${anime.animeId})">📖</button>
                        <button class="action-btn" title="刷新此源" onclick="handleSourceAction('refresh', ${source.source_id}, '${anime.title}')">🔄</button>
                        <button class="action-btn" title="删除此源" onclick="handleSourceAction('delete', ${source.source_id}, '${anime.title}')">🗑️</button>
                    </div>
                `;
            });
        } else {
            sourceTableBody.innerHTML = `<tr><td colspan="4">未关联任何数据源。</td></tr>`;
        }

        // 重新绑定事件监听器
        document.getElementById('back-to-library-btn').addEventListener('click', () => {
            animeDetailView.classList.add('hidden');
            libraryView.classList.remove('hidden');
        });

    }

    function refreshSource(sourceId, title) {
        if (confirm(`您确定要为 '${title}' 的这个数据源执行全量刷新吗？`)) {
            apiFetch(`/api/ui/library/source/${sourceId}/refresh`, {
                method: 'POST',
            }).then(response => {
                alert(response.message || "刷新任务已开始，请在日志中查看进度。");
            }).catch(error => {
                alert(`启动刷新任务失败: ${(error.message || error)}`);
            });
        }
    }

    function showEditAnimeView(animeId, currentTitle, currentSeason) {
        libraryView.classList.add('hidden');
        animeDetailView.classList.add('hidden');
        episodeListView.classList.add('hidden');
        editAnimeView.classList.remove('hidden');

        document.getElementById('edit-anime-id').value = animeId;
        document.getElementById('edit-anime-title').value = currentTitle;
        document.getElementById('edit-anime-season').value = currentSeason;
    }

    // --- Episode List View ---
    async function showEpisodeListView(sourceId, animeTitle, animeId) {
        animeDetailView.classList.add('hidden');
        editEpisodeView.classList.add('hidden');
        episodeListView.classList.remove('hidden');
        episodeListView.innerHTML = '<div>加载中...</div>';

        try {
            const episodes = await apiFetch(`/api/ui/library/source/${sourceId}/episodes`);
            renderEpisodeListView(sourceId, animeTitle, episodes, animeId);
        } catch (error) {
            episodeListView.innerHTML = `<div class="error">加载分集列表失败: ${(error.message || error)}</div>`;
        }
    }

    function renderEpisodeListView(sourceId, animeTitle, episodes, animeId) {
        let html = `
            <div class="episode-list-header">
                <h3>分集列表: ${animeTitle}</h3>
                <button id="back-to-detail-view-btn">&lt; 返回作品详情</button>
            </div>
            <table id="episode-list-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>剧集名</th>
                        <th>集数</th>
                        <th>弹幕数</th>
                        <th>采集时间</th>
                        <th>官方链接</th>
                        <th>剧集操作</th>
                    </tr>
                </thead>
                <tbody>
                </tbody>
            </table>
        `;
        episodeListView.innerHTML = html;

        // Store context on the view container for handleEpisodeAction to use
        episodeListView.dataset.sourceId = sourceId;
        episodeListView.dataset.animeTitle = animeTitle;
        episodeListView.dataset.animeId = animeId;

        const episodeTableBody = episodeListView.querySelector('#episode-list-table tbody');
        if (episodes.length > 0) {
            episodes.forEach(ep => {
                const row = episodeTableBody.insertRow();
                row.insertCell().textContent = ep.id;
                row.insertCell().textContent = ep.title;
                row.insertCell().textContent = ep.episode_index;
                row.insertCell().textContent = ep.comment_count;
                row.insertCell().textContent = ep.fetched_at ? new Date(ep.fetched_at).toLocaleString() : 'N/A';
                
                const linkCell = row.insertCell();
                if (ep.source_url) {
                    const link = document.createElement('a');
                    link.href = ep.source_url;
                    link.textContent = '跳转';
                    link.target = '_blank';
                    linkCell.appendChild(link);
                } else {
                    linkCell.textContent = '无';
                }

                const actionsCell = row.insertCell();
                actionsCell.className = 'actions-cell';
                actionsCell.innerHTML = `
                    <div class="action-buttons-wrapper">
                        <button class="action-btn" title="编辑剧集" onclick="handleEpisodeAction('edit', ${ep.id}, '${ep.title.replace(/'/g, "\\'")}')">✏️</button>
                        <button class="action-btn" title="刷新剧集" onclick="handleEpisodeAction('refresh', ${ep.id}, '${ep.title.replace(/'/g, "\\'")}')">🔄</button>
                        <button class="action-btn" title="查看具体弹幕" onclick="handleEpisodeAction('view_danmaku', ${ep.id}, '${ep.title.replace(/'/g, "\\'")}')">💬</button>
                        <button class="action-btn" title="删除集" onclick="handleEpisodeAction('delete', ${ep.id}, '${ep.title.replace(/'/g, "\\'")}')">🗑️</button>
                    </div>
                `;
            });
        } else {
            episodeTableBody.innerHTML = `<tr><td colspan="7">未找到任何分集数据。</td></tr>`;
        }

        // 重新绑定事件监听器
        document.getElementById('back-to-detail-view-btn').addEventListener('click', () => {
            episodeListView.classList.add('hidden');
            showAnimeDetailView(animeId);
        });

    }

    async function showDanmakuListView(episodeId, episodeTitle, sourceId, animeTitle, animeId) {
        episodeListView.classList.add('hidden');
        editEpisodeView.classList.add('hidden');
        danmakuListView.classList.remove('hidden');
        danmakuListView.innerHTML = '<div>加载中...</div>';

        try {
            const data = await apiFetch(`/api/ui/comment/${episodeId}`);
            renderDanmakuListView(episodeId, episodeTitle, sourceId, animeTitle, animeId, data.comments);
        } catch (error) {
            danmakuListView.innerHTML = `<div class="error">加载弹幕失败: ${(error.message || error)}</div>`;
        }
    }

    function renderDanmakuListView(episodeId, episodeTitle, sourceId, animeTitle, animeId, comments) {
        let html = `
            <div class="episode-list-header">
                <h3>弹幕列表: ${animeTitle} - ${episodeTitle}</h3>
                <button id="back-to-episodes-from-danmaku-btn">&lt; 返回分集列表</button>
            </div>
            <pre id="danmaku-content-pre"></pre>
        `;
        danmakuListView.innerHTML = html;

        const danmakuContentPre = document.getElementById('danmaku-content-pre');
        if (comments.length === 0) {
            danmakuContentPre.textContent = '该分集没有弹幕。';
        } else {
            const formattedText = comments.map(c => `${c.p} | ${c.m}`).join('\n');
            danmakuContentPre.textContent = formattedText;
        }

        // 重新绑定事件监听器
        document.getElementById('back-to-episodes-from-danmaku-btn').addEventListener('click', () => {
            danmakuListView.classList.add('hidden');
            showEpisodeListView(sourceId, animeTitle, animeId);
        });
    }

    async function loadAndRenderTokens() {
        if (!tokenTableBody) return;
        tokenTableBody.innerHTML = '<tr><td colspan="5">加载中...</td></tr>';
        try {
            const tokens = await apiFetch('/api/ui/tokens');
            renderTokens(tokens);
        } catch (error) {
            tokenTableBody.innerHTML = `<tr><td colspan="5" class="error">加载失败: ${(error.message || error)}</td></tr>`;
        }
    }

    async function loadCustomDomain() {
        domainSaveMessage.textContent = '';
        domainSaveMessage.className = 'message';
        try {
            const data = await apiFetch('/api/ui/config/custom_api_domain');
            customDomainInput.value = data.value || '';
        } catch (error) {
            domainSaveMessage.textContent = `加载域名失败: ${(error.message || error)}`;
            domainSaveMessage.classList.add('error');
        }
    }

    function renderTokens(tokens) {
        tokenTableBody.innerHTML = '';
        if (tokens.length === 0) {
            tokenTableBody.innerHTML = '<tr><td colspan="5">没有创建任何Token。</td></tr>';
            return;
        }

        tokens.forEach(token => {
            const row = tokenTableBody.insertRow();
            row.insertCell().textContent = token.name;

            const tokenCell = row.insertCell();
            const tokenSpan = document.createElement('span');
            tokenSpan.className = 'token-value';
            tokenSpan.textContent = token.token;
            tokenCell.appendChild(tokenSpan);

            const statusCell = row.insertCell();
            statusCell.textContent = token.is_enabled ? '✅' : '❌';
            statusCell.className = token.is_enabled ? 'token-status' : 'token-status disabled';

            row.insertCell().textContent = new Date(token.created_at).toLocaleString();

            const actionsCell = row.insertCell();
            actionsCell.className = 'actions-cell';
            const enabledText = token.is_enabled ? '禁用' : '启用';
            actionsCell.innerHTML = `
                <div class="action-buttons-wrapper">
                    <button class="action-btn" title="复制链接" onclick="handleTokenAction('copy', ${token.id}, '${token.token}')">📋</button>
                    <button class="action-btn" title="${enabledText}" onclick="handleTokenAction('toggle', ${token.id})">${token.is_enabled ? '⏸️' : '▶️'}</button>
                    <button class="action-btn" title="删除" onclick="handleTokenAction('delete', ${token.id})">🗑️</button>
                </div>
            `;
        });
    }

    function showEditEpisodeView(episodeId, episodeTitle, episodeIndex, sourceUrl, sourceId, animeTitle, animeId) {
        episodeListView.classList.add('hidden');
        animeDetailView.classList.add("hidden");
        editEpisodeView.classList.remove('hidden');

        // Populate form
        document.getElementById('edit-episode-id').value = episodeId;
        document.getElementById('edit-episode-title').value = episodeTitle;
        document.getElementById('edit-episode-index').value = episodeIndex;
        document.getElementById('edit-episode-url').value = sourceUrl;
        

        // Store context for navigating back
        document.getElementById('edit-episode-source-id').value = sourceId;
        document.getElementById('edit-episode-anime-title').value = animeTitle;
        document.getElementById('edit-episode-anime-id').value = animeId;
    }

    // --- Global Action Handlers ---
    window.handleAction = (action, animeId) => {
        const row = document.querySelector(`#library-table button[onclick*="handleAction('${action}', ${animeId})"]`).closest('tr');
        const title = row ? row.cells[1].textContent : `ID: ${animeId}`;

        if (action === 'delete') {
            if (confirm(`您确定要删除番剧 '${title}' 吗？\n此操作将删除其所有分集和弹幕，且不可恢复。`)) {
                apiFetch(`/api/ui/library/anime/${animeId}`, {
                    method: 'DELETE',
                }).then(() => {
                    loadLibrary();
                }).catch(error => {
                    alert(`删除失败: ${(error.message || error)}`);
                });
            }
        } else if (action === 'edit') {
            const currentSeason = row ? parseInt(row.cells[2].textContent, 10) : 1;
            showEditAnimeView(animeId, title, currentSeason);
        } else if (action === 'view') {
            showAnimeDetailView(animeId);
        } else {
            alert(`功能 '${action}' 尚未实现。`);
        }
    };

    window.handleEpisodeAction = (action, episodeId, title) => {
        const row = document.querySelector(`#episode-list-table button[onclick*="handleEpisodeAction('${action}', ${episodeId},"]`).closest('tr');
        
        // Retrieve context from the view container's dataset
        const sourceId = parseInt(episodeListView.dataset.sourceId, 10);
        const animeTitle = episodeListView.dataset.animeTitle;
        const animeId = parseInt(episodeListView.dataset.animeId, 10);

        if (isNaN(animeId) || isNaN(sourceId)) {
            alert("无法获取上下文信息，操作失败。");
            return;
        }

        if (action === 'delete') {
            if (confirm(`您确定要删除分集 '${title}' 吗？\n此操作将删除该分集及其所有弹幕，且不可恢复。`)) {
                apiFetch(`/api/ui/library/episode/${episodeId}`, {
                    method: 'DELETE',
                }).then(() => {
                    if (row) row.remove();
                }).catch(error => {
                    alert(`删除失败: ${(error.message || error)}`);
                });
            }
        } else if (action === 'edit') {
            const episodeIndex = row.cells[2].textContent;
            // 关键修复：弹幕数列(3)和采集时间列(4)被添加后，链接列的索引是 5
            const sourceUrl = row.cells[5] && row.cells[5].querySelector('a') ? row.cells[5].querySelector('a').href : '';
            showEditEpisodeView(episodeId, title, episodeIndex, sourceUrl, sourceId, animeTitle, animeId);
        } else if (action === 'refresh') {
            if (confirm(`您确定要刷新分集 '${title}' 的弹幕吗？\n这将清空现有弹幕并从源重新获取。`)) {
                apiFetch(`/api/ui/library/episode/${episodeId}/refresh`, { method: 'POST' })
                    .then(response => alert(response.message || "刷新任务已开始。"))
                    .catch(error => alert(`启动刷新任务失败: ${(error.message || error)}`));
            }
        } else if (action === 'view_danmaku') {
            showDanmakuListView(episodeId, title, sourceId, animeTitle, animeId);
        }
    };

    window.handleSourceAction = (action, sourceId, title, animeId = null) => {
        if (action === 'refresh') {
            refreshSource(sourceId, title);
        } else if (action === 'view_episodes' && animeId) {
            showEpisodeListView(sourceId, title, animeId);
        } else if (action === 'delete') {
            // Placeholder for deleting a source
            alert(`功能 '删除源' (ID: ${sourceId}) 尚未实现。`);
        } else if (action === 'favorite') {
            apiFetch(`/api/ui/library/source/${sourceId}/favorite`, {
                method: 'PUT',
            }).then(() => {
                showAnimeDetailView(animeId); // 刷新视图以显示更新后的状态
            }).catch(error => {
                alert(`操作失败: ${error.message}`);
            });
        }
    };

    window.handleTokenAction = async (action, tokenId, tokenValue = '') => {
        if (action === 'copy') {
            const domain = document.getElementById('custom-domain-input').value.trim();
            const textToCopy = domain ? `${domain}/api/${tokenValue}` : tokenValue;
            
            // 优先使用现代的、安全的剪贴板API
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(textToCopy).then(() => {
                    alert(`已复制到剪贴板: ${textToCopy}`);
                }, (err) => {
                    alert(`复制失败: ${err}。请手动复制。`);
                });
            } else {
                // 为 HTTP 或旧版浏览器提供后备方案
                const textArea = document.createElement("textarea");
                textArea.value = textToCopy;
                textArea.style.position = "fixed";
                textArea.style.top = "-9999px";
                textArea.style.left = "-9999px";
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                try {
                    document.execCommand('copy');
                    alert(`已复制到剪贴板: ${textToCopy}`);
                } catch (err) {
                    alert('复制失败，请手动复制。');
                }
                document.body.removeChild(textArea);
            }
        } else if (action === 'toggle') {
            try {
                await apiFetch(`/api/ui/tokens/${tokenId}/toggle`, { method: 'PUT' });
                loadAndRenderTokens();
            } catch (error) {
                alert(`操作失败: ${error.message}`);
            }
        } else if (action === 'delete') {
            if (confirm("您确定要删除这个Token吗？此操作不可恢复。")) {
                try {
                    await apiFetch(`/api/ui/tokens/${tokenId}`, { method: 'DELETE' });
                    loadAndRenderTokens();
                } catch (error) {
                    alert(`删除失败: ${error.message}`);
                }
            }
        }
    };

    // --- Initial Load ---
    setupEventListeners();
    checkLogin();
});
