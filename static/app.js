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
    const clearCacheBtn = document.getElementById('clear-cache-btn');
    const bulkImportBtn = document.getElementById('bulk-import-btn');
    const selectAllBtn = document.getElementById('select-all-btn');
    const resultsFilterControls = document.getElementById('results-filter-controls');
    const filterBtnMovie = document.getElementById('filter-btn-movie');
    const filterBtnTvSeries = document.getElementById('filter-btn-tv_series');
    const resultsFilterInput = document.getElementById('results-filter-input');
    const logOutput = document.getElementById('log-output');
    const loader = document.getElementById('loader');
    const testMatchForm = document.getElementById('test-match-form');
    const testTokenInput = document.getElementById('test-token-input');
    const testFilenameInput = document.getElementById('test-filename-input');
    const testMatchResults = document.getElementById('test-match-results');
    
    const changePasswordForm = document.getElementById('change-password-form');
    const passwordChangeMessage = document.getElementById('password-change-message');

    const libraryTableBody = document.querySelector('#library-table tbody');
    const libraryView = document.getElementById('library-view');
    const animeDetailView = document.getElementById('anime-detail-view');
    const detailViewImg = document.getElementById('detail-view-img');
    const detailViewTitle = document.getElementById('detail-view-title');
    const detailViewMeta = document.getElementById('detail-view-meta');
    const sourceDetailTableBody = document.getElementById('source-detail-table-body');

    const editAnimeView = document.getElementById('edit-anime-view');
    const settingsView = document.getElementById('settings-view');
    const episodeListView = document.getElementById('episode-list-view');
    const danmakuListView = document.getElementById('danmaku-list-view');
    const editEpisodeView = document.getElementById('edit-episode-view');
    const editAnimeTypeSelect = document.getElementById('edit-anime-type');
    const editAnimeSeasonInput = document.getElementById('edit-anime-season');
    const editEpisodeForm = document.getElementById('edit-episode-form');
    const editAnimeForm = document.getElementById('edit-anime-form');
    const librarySearchInput = document.getElementById('library-search-input');

    // Bangumi Settings Elements
    const bangumiAuthStateUnauthenticated = document.getElementById('bangumi-auth-state-unauthenticated');
    const bangumiAuthStateAuthenticated = document.getElementById('bangumi-auth-state-authenticated');
    const bangumiUserNickname = document.getElementById('bangumi-user-nickname');
    const bangumiUserId = document.getElementById('bangumi-user-id');
    const bangumiAuthorizedAt = document.getElementById('bangumi-authorized-at');
    const bangumiExpiresAt = document.getElementById('bangumi-expires-at');
    const bangumiUserAvatar = document.getElementById('bangumi-user-avatar');
    const bangumiLoginBtn = document.getElementById('bangumi-login-btn');
    const bangumiLogoutBtn = document.getElementById('bangumi-logout-btn');

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

    const settingsSubNav = document.querySelector('.settings-sub-nav');
    const settingsSubViews = document.querySelectorAll('.settings-subview');

    // Bangumi Search View Elements
    const bangumiSearchView = document.getElementById('bangumi-search-view');
    const bangumiSearchViewTitle = document.getElementById('bangumi-search-view-title');
    const bangumiSearchForm = document.getElementById('bangumi-search-form');
    const bangumiSearchKeywordInput = document.getElementById('bangumi-search-keyword');
    const bangumiSearchResultsList = document.getElementById('bangumi-search-results-list');
    const backToEditAnimeFromBgmSearchBtn = document.getElementById('back-to-edit-anime-from-bgm-search-btn');

    // TMDB Search View Elements
    const tmdbSearchView = document.getElementById('tmdb-search-view');
    const tmdbSearchForm = document.getElementById('tmdb-search-form');
    const tmdbSearchResultsList = document.getElementById('tmdb-search-results-list');

    // EGID Modal Elements
    const selectEgidBtn = document.getElementById('select-egid-btn');
    const viewEgidEpisodesBtn = document.getElementById('view-egid-episodes-btn');
    const egidSelectionModal = document.getElementById('egid-selection-modal');
    const egidSelectionList = document.getElementById('egid-selection-list');
    const closeEgidSelectionModalBtn = document.getElementById('close-egid-selection-modal-btn');
    const egidEpisodesModal = document.getElementById('egid-episodes-modal');
    const egidEpisodesModalTitle = document.getElementById('egid-episodes-modal-title');
    const egidEpisodesListContainer = document.getElementById('egid-episodes-list-container');
    const closeEgidEpisodesModalBtn = document.getElementById('close-egid-episodes-modal-btn');
    // --- State ---
    let token = localStorage.getItem('danmu_api_token');
    let logRefreshInterval = null;
    let currentEpisodes = []; // 用于存储当前分集列表的上下文
    let originalSearchResults = []; // 用于存储原始搜索结果以进行前端过滤
    let _currentSearchSelectionData = null; // 用于存储搜索选择的数据，以供“应用”按钮使用

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

    async function logout() {
        try {
            // 调用登出API以清除服务器端的HttpOnly cookie
            await apiFetch('/api/ui/auth/logout', { method: 'POST' });
        } catch (error) {
            console.error("Logout API call failed:", error.message);
            // 即使API调用失败，也继续执行客户端的登出流程
        } finally {
            token = null;
            localStorage.removeItem('danmu_api_token');
            showView('auth');
            stopLogRefresh();
        }
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
        // Forms
        loginForm.addEventListener('submit', handleLogin);
        searchForm.addEventListener('submit', handleSearch);
        testMatchForm.addEventListener('submit', handleTestMatch);
        changePasswordForm.addEventListener('submit', handleChangePassword);
        editAnimeForm.addEventListener('submit', handleEditAnimeSave);
        editEpisodeForm.addEventListener('submit', handleEditEpisodeSave);

        // Sidebar Navigation
        sidebar.addEventListener('click', handleSidebarNavigation);

        editAnimeTypeSelect.addEventListener('change', handleAnimeTypeChange);
        // Buttons
        logoutBtn.addEventListener('click', logout);
        clearCacheBtn.addEventListener('click', handleClearCache);
        bulkImportBtn.addEventListener('click', handleBulkImport);
        selectAllBtn.addEventListener('click', handleSelectAll);
        bangumiLoginBtn.addEventListener('click', handleBangumiLogin);
        bangumiLogoutBtn.addEventListener('click', handleBangumiLogout);
        // Filter controls
        filterBtnMovie.addEventListener('click', handleTypeFilterClick);
        filterBtnTvSeries.addEventListener('click', handleTypeFilterClick);
        resultsFilterInput.addEventListener('input', applyFiltersAndRender);
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
        document.getElementById('back-to-library-from-detail-btn').addEventListener('click', () => {
            animeDetailView.classList.add('hidden');
            libraryView.classList.remove('hidden');
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

        // Special listener for BGM ID search button
        document.getElementById('search-bgmid-btn').addEventListener('click', handleSearchBgmId);
        // Special listener for TMDB ID search button
        document.getElementById('search-tmdbid-btn').addEventListener('click', handleSearchTmdbId);
        // Listener for OAuth popup completion
        window.addEventListener('message', handleOAuthCallbackMessage);
        // New listeners for Bangumi Search View
        backToEditAnimeFromBgmSearchBtn.addEventListener('click', handleBackToEditAnime);
        bangumiSearchForm.addEventListener('submit', handleBangumiSearchSubmit);
        // New listeners for TMDB Search View
        document.getElementById('back-to-edit-anime-from-tmdb-search-btn').addEventListener('click', handleBackToEditAnime);
        tmdbSearchForm.addEventListener('submit', handleTmdbSearchSubmit);

        // New listeners for EGID functionality
        selectEgidBtn.addEventListener('click', handleSelectEgidClick);
        viewEgidEpisodesBtn.addEventListener('click', handleViewEgidEpisodesClick);
        closeEgidSelectionModalBtn.addEventListener('click', () => egidSelectionModal.classList.add('hidden'));
        closeEgidEpisodesModalBtn.addEventListener('click', () => egidEpisodesModal.classList.add('hidden'));
        egidSelectionList.addEventListener('click', handleEgidSelection);
        document.getElementById('edit-anime-tmdbid').addEventListener('input', updateEgidButtonStates);
        document.getElementById('edit-anime-egid').addEventListener('input', updateEgidButtonStates);
        document.getElementById('tmdb-settings-form').addEventListener('submit', handleSaveTmdbSettings);

        // Listener for "apply" buttons in edit form (using event delegation)
        editAnimeForm.addEventListener('click', (e) => {
            if (e.target.classList.contains('apply-btn')) {
                const wrapper = e.target.parentElement;
                const input = wrapper.querySelector('input');
                if (input) {
                    input.value = e.target.dataset.newValue || '';
                    e.target.remove(); // Apply and then remove the button
                }
            }
        });
        settingsSubNav.addEventListener('click', handleSettingsSubNav);
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
            } else if (viewId === 'settings-view') {
                // When switching to settings, activate the first sub-navigation tab by default
                const firstSubNavBtn = settingsSubNav.querySelector('.sub-nav-btn');
                if (firstSubNavBtn) {
                    firstSubNavBtn.click();
                }
            }
        }
    }

    function handleAnimeTypeChange() {
        const isMovie = editAnimeTypeSelect.value === 'movie';
        
        // Get related elements
        const seasonInput = document.getElementById('edit-anime-season');
        const egidInput = document.getElementById('edit-anime-egid');
        const seasonIndicator = seasonInput.nextElementSibling;
        const egidWrapper = egidInput.closest('.input-with-icon');
        const egidIndicator = egidWrapper ? egidWrapper.nextElementSibling : null;
        const egidSelectBtn = document.getElementById('select-egid-btn');
        const egidViewBtn = document.getElementById('view-egid-episodes-btn');

        // Handle Season input
        seasonInput.disabled = isMovie;
        if (isMovie) {
            seasonInput.value = 1;
        }
        if (seasonIndicator?.classList.contains('disabled-indicator')) {
            seasonIndicator.classList.toggle('hidden', !isMovie);
        }

        // Handle Episode Group ID input
        egidInput.disabled = isMovie;
        egidSelectBtn.disabled = isMovie;
        egidViewBtn.disabled = isMovie;
        egidWrapper?.classList.toggle('disabled', isMovie);
        if (egidIndicator?.classList.contains('disabled-indicator')) {
            egidIndicator.classList.toggle('hidden', !isMovie);
        }
        if (isMovie) {
            egidInput.value = ''; // Clear the value when disabled
        }
        updateEgidButtonStates(); // Re-evaluate button states
    }

    function updateEgidButtonStates() {
        const tmdbId = document.getElementById('edit-anime-tmdbid').value.trim();
        const egid = document.getElementById('edit-anime-egid').value.trim();
        const isMovie = document.getElementById('edit-anime-type').value === 'movie';

        // Select button is enabled if there's a TMDB ID and it's not a movie
        selectEgidBtn.disabled = !tmdbId || isMovie;
        // View button is enabled if there's an EGID
        viewEgidEpisodesBtn.disabled = !egid || isMovie;
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

    async function handleTestMatch(e) {
        e.preventDefault();
        const apiToken = testTokenInput.value.trim();
        const filename = testFilenameInput.value.trim();
        if (!apiToken || !filename) {
            alert('Token和文件名都不能为空。');
            return;
        }

        testMatchResults.textContent = '正在测试...';
        const testButton = testMatchForm.querySelector('button');
        testButton.disabled = true;

        try {
            const data = await apiFetch(`/api/${apiToken}/match`, {
                method: 'POST',
                body: JSON.stringify({ fileName: filename })
            });

            if (data.success === false) { // 来自 DandanApiRoute 的错误
                 testMatchResults.textContent = `测试失败: [${data.errorCode}] ${data.errorMessage}`;
                 return;
            }

            if (data.isMatched) {
                const match = data.matches[0];
                testMatchResults.textContent = `[匹配成功]\n` +
                    `番剧: ${match.animeTitle} (ID: ${match.animeId})\n` +
                    `分集: ${match.episodeTitle} (ID: ${match.episodeId})\n` +
                    `类型: ${match.typeDescription}`;
            } else if (data.matches && data.matches.length > 0) {
                const formattedResults = data.matches.map(match =>
                    `- [多个可能] ${match.animeTitle} - ${match.episodeTitle} (ID: ${match.episodeId})`
                ).join('\n');
                testMatchResults.textContent = `匹配不唯一，找到 ${data.matches.length} 个可能的结果 (isMatched=false):\n${formattedResults}`;
            } else {
                testMatchResults.textContent = '未匹配到任何结果。';
            }
        } catch (error) {
            testMatchResults.textContent = `请求失败: ${(error.message || error)}`;
        } finally {
            testButton.disabled = false;
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
        const newSeason = parseInt(document.getElementById('edit-anime-season').value, 10);

        if (isNaN(newSeason) || newSeason < 1) {
            alert("季度数必须是一个大于0的数字。");
            return;
        }

        const payload = {
            title: document.getElementById('edit-anime-title').value,
            type: document.getElementById('edit-anime-type').value,
            season: newSeason,
            tmdb_id: document.getElementById('edit-anime-tmdbid').value || null,
            tmdb_episode_group_id: document.getElementById('edit-anime-egid').value || null,
            bangumi_id: document.getElementById('edit-anime-bgmid').value || null,
            tvdb_id: document.getElementById('edit-anime-tvdbid').value || null,
            douban_id: document.getElementById('edit-anime-doubanid').value || null,
            imdb_id: document.getElementById('edit-anime-imdbid').value || null,
            name_en: document.getElementById('edit-anime-name-en').value || null,
            name_jp: document.getElementById('edit-anime-name-jp').value || null,
            name_romaji: document.getElementById('edit-anime-name-romaji').value || null,
            alias_cn_1: document.getElementById('edit-anime-alias-cn-1').value || null,
            alias_cn_2: document.getElementById('edit-anime-alias-cn-2').value || null,
            alias_cn_3: document.getElementById('edit-anime-alias-cn-3').value || null,
        };

        const saveButton = editAnimeForm.querySelector('button[type="submit"]');
        saveButton.disabled = true;
        saveButton.textContent = '保存中...';

        try {
            await apiFetch(`/api/ui/library/anime/${animeId}`, {
                method: 'PUT',
                body: JSON.stringify(payload),
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

    async function handleSaveTmdbSettings(e) {
        e.preventDefault();
        const apiKey = document.getElementById('tmdb-api-key').value.trim();
        const apiBaseUrl = document.getElementById('tmdb-api-base-url').value.trim();
        const imageBaseUrl = document.getElementById('tmdb-image-base-url').value.trim();
        
        const saveBtn = e.target.querySelector('button[type="submit"]');
        const messageEl = document.getElementById('tmdb-save-message');

        saveBtn.disabled = true;
        messageEl.textContent = '保存中...';
        messageEl.className = 'message';

        try {
            await apiFetch('/api/ui/config/tmdb', {
                method: 'PUT',
                body: JSON.stringify({
                    tmdb_api_key: apiKey,
                    tmdb_api_base_url: apiBaseUrl,
                    tmdb_image_base_url: imageBaseUrl
                })
            });
            messageEl.textContent = 'TMDB 配置保存成功！';
            messageEl.classList.add('success');
        } catch (error) {
            messageEl.textContent = `保存失败: ${error.message}`;
            messageEl.classList.add('error');
        } finally {
            saveBtn.disabled = false;
        }
    }

    async function handleBangumiLogin() {
        try {
            const { url } = await apiFetch('/api/bgm/auth/url');
            window.open(url, 'BangumiAuth', 'width=600,height=700');
        } catch (error) {
            alert(`启动 Bangumi 授权失败: ${error.message}`);
        }
    }

    function handleOAuthCallbackMessage(event) {
        // We don't check event.origin for simplicity, but in production, you should.
        // e.g., if (event.origin !== 'https://your-app-domain.com') return;
        if (event.data === 'BANGUMI-OAUTH-COMPLETE') {
            console.log("收到 Bangumi OAuth 完成消息，正在刷新状态...");
            loadBangumiAuthState();
        }
    }

    async function handleBangumiLogout() {
        if (confirm("确定要注销 Bangumi 授权吗？")) {
            try {
                await apiFetch('/api/bgm/auth', { method: 'DELETE' });
                loadBangumiAuthState();
            } catch (error) {
                alert(`注销失败: ${error.message}`);
            }
        }
    }

    async function handleBulkImport() {
        const selectedCheckboxes = resultsList.querySelectorAll('input[type="checkbox"]:checked');
        const selectedMediaIds = new Set(Array.from(selectedCheckboxes).map(checkbox => checkbox.value));

        if (selectedMediaIds.size === 0) {
            alert("请选择要导入的媒体。");
            return;
        }

        if (!confirm(`确定要批量导入 ${selectedMediaIds.size} 个媒体吗？`)) {
            return;
        }

        bulkImportBtn.disabled = true;
        bulkImportBtn.textContent = '批量导入中...';

        const itemsToImport = originalSearchResults.filter(item => selectedMediaIds.has(item.mediaId));

        try {
            for (const item of itemsToImport) {
                try {
                    const data = await apiFetch('/api/ui/import', {
                        method: 'POST',
                        body: JSON.stringify({
                            provider: item.provider,
                            media_id: item.mediaId,
                            anime_title: item.title,
                            type: item.type,
                            image_url: item.imageUrl,
                            douban_id: item.douban_id,
                            current_episode_index: item.currentEpisodeIndex,
                        }),
                    });
                    console.log(`提交导入任务 ${item.title} 成功: ${data.message}`);
                } catch (error) {
                    console.error(`提交导入任务 ${item.title} 失败: ${error.message || error}`);
                }
                // A small delay to prevent overwhelming the server
                await new Promise(resolve => setTimeout(resolve, 200));
            }
            alert("批量导入任务已提交，请在任务管理器中查看进度。");
        } finally {
            bulkImportBtn.disabled = false;
            bulkImportBtn.textContent = '批量导入';
        }
    }

    function handleSelectAll() {
        const checkboxes = resultsList.querySelectorAll('input[type="checkbox"]');
        if (checkboxes.length === 0) return;
        // 如果有任何一个没被选中，则全部选中；否则全部不选。
        const shouldCheckAll = Array.from(checkboxes).some(cb => !cb.checked);
        checkboxes.forEach(cb => {
            cb.checked = shouldCheckAll;
        });
    }

    function handleTypeFilterClick(e) {
        const btn = e.currentTarget;
        btn.classList.toggle('active');
        const icon = btn.querySelector('.status-icon');
        icon.textContent = btn.classList.contains('active') ? '✅' : '❌';
        applyFiltersAndRender();
    }
    async function handleClearCache() {
        if (confirm("您确定要清除所有缓存吗？\n这将清除所有搜索结果和分集列表的临时缓存，下次访问时需要重新从网络获取。")) {
            try {
                const response = await apiFetch('/api/ui/cache/clear', {
                    method: 'POST'
                });
                alert(response.message || "缓存已成功清除！");
            } catch (error) {
                alert(`清除缓存失败: ${(error.message || error)}`);
            }
        }
    }
    // --- Task Manager View (Optimized Rendering) ---
    function renderTasks(tasks) {
        if (!taskListUl) return;

        // If no tasks, show message and clear list
        if (tasks.length === 0) {
            taskListUl.innerHTML = '<li>当前没有任务。</li>';
            return;
        }

        // 如果列表之前显示的是“没有任务”的消息，则先清空它
        const noTasksLi = taskListUl.querySelector('li:not(.task-item)');
        if (noTasksLi) {
            taskListUl.innerHTML = '';
        }

        const existingTaskElements = new Map([...taskListUl.querySelectorAll('.task-item')].map(el => [el.dataset.taskId, el]));
        const incomingTaskIds = new Set(tasks.map(t => t.task_id));

        // Remove tasks that are no longer in the list (e.g., if backend state is cleared)
        for (const [taskId, element] of existingTaskElements.entries()) {
            if (!incomingTaskIds.has(taskId)) {
                element.remove();
            }
        }

        // Update existing or add new tasks
        tasks.forEach(task => {
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
            }
        });
    }

    // Start polling tasks when the app is loaded and user is logged in
    setInterval(loadAndRenderTasks, 800);

    // --- Rendering Functions ---

    function renderSearchResults(results) {
        resultsList.innerHTML = '';
        if (results.length === 0) {
            resultsList.innerHTML = '<li>没有符合筛选条件的结果。</li>';
            return;
        }
        results.forEach(item => {
            const li = document.createElement('li');
            
            const leftContainer = document.createElement('div');
            leftContainer.className = 'result-item-left';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = item.mediaId;
            leftContainer.appendChild(checkbox);

            const posterImg = document.createElement('img');
            posterImg.className = 'poster';
            posterImg.src = item.imageUrl || '/static/placeholder.png';
            posterImg.referrerPolicy = 'no-referrer';
            posterImg.alt = item.title;
            leftContainer.appendChild(posterImg);

            const infoDiv = document.createElement('div');
            infoDiv.className = 'info';

            const titleP = document.createElement('p');
            titleP.className = 'title';
            titleP.textContent = item.title;
            infoDiv.appendChild(titleP);

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
            infoDiv.appendChild(metaP);
            leftContainer.appendChild(infoDiv);

            li.appendChild(leftContainer);

            const importBtn = document.createElement('button');
            importBtn.textContent = '导入弹幕';
            importBtn.addEventListener('click', () => handleImportClick(importBtn, item));

            li.appendChild(importBtn);
            resultsList.appendChild(li);
        });
    }

    function applyFiltersAndRender() {
        if (!originalSearchResults) return;

        // 1. Type filtering (higher priority)
        const activeTypes = new Set();
        if (filterBtnMovie.classList.contains('active')) {
            activeTypes.add('movie');
        }
        if (filterBtnTvSeries.classList.contains('active')) {
            activeTypes.add('tv_series');
        }

        let filteredResults = originalSearchResults.filter(item => activeTypes.has(item.type));

        // 2. Text filtering
        const filterText = resultsFilterInput.value.toLowerCase();
        if (filterText) {
            filteredResults = filteredResults.filter(item => item.title.toLowerCase().includes(filterText));
        }

        // 3. Render
        renderSearchResults(filteredResults);
    }

    function displayResults(results) {
        originalSearchResults = results;
        resultsFilterControls.classList.toggle('hidden', results.length === 0);

        if (results.length > 0) {
            // Reset filters to default state
            filterBtnMovie.classList.add('active');
            filterBtnMovie.querySelector('.status-icon').textContent = '✅';
            filterBtnTvSeries.classList.add('active');
            filterBtnTvSeries.querySelector('.status-icon').textContent = '✅';
            resultsFilterInput.value = '';
            applyFiltersAndRender();
        } else {
            resultsList.innerHTML = '<li>未找到结果。</li>';
        }
    }

    async function handleImportClick(button, item) {
        button.disabled = true;
        button.textContent = '导入中...';
        try {
            const data = await apiFetch('/api/ui/import', {
                method: 'POST',
                body: JSON.stringify({
                    provider: item.provider,
                    media_id: item.mediaId,
                    anime_title: item.title,
                    type: item.type,
                    image_url: item.imageUrl,
                    douban_id: item.douban_id,
                    current_episode_index: item.currentEpisodeIndex,
                }),
            });
            alert(data.message);
        } catch (error) {
            alert(`提交导入任务失败: ${(error.message || error)}`);
        } finally {
            button.disabled = false;
            button.textContent = '导入弹幕';
        }
    }

    async function loadLibrary() {
        if (!libraryTableBody) return;
        libraryTableBody.innerHTML = '<tr><td colspan="8">加载中...</td></tr>';
        try {
            const data = await apiFetch('/api/ui/library');
            renderLibrary(data.animes);
        } catch (error) {
            libraryTableBody.innerHTML = `<tr><td colspan="8" class="error">加载失败: ${(error.message || error)}</td></tr>`;
        }
    }

    function renderLibrary(animes) {
        libraryTableBody.innerHTML = '';
        if (animes.length === 0) {
            libraryTableBody.innerHTML = '<tr><td colspan="8">媒体库为空。</td></tr>';
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

            const typeCell = row.insertCell();
            const typeMap = {
                'tv_series': '电视节目',
                'movie': '电影/剧场版',
                'ova': 'OVA',
                'other': '其他'
            };
            typeCell.textContent = typeMap[anime.type] || anime.type;
            row.insertCell().textContent = anime.season;
            row.insertCell().textContent = anime.episodeCount;
            row.insertCell().textContent = anime.sourceCount;
            row.insertCell().textContent = new Date(anime.createdAt).toLocaleString();

            const actionsCell = row.insertCell();
            actionsCell.className = 'actions-cell';

            const wrapper = document.createElement('div');
            wrapper.className = 'action-buttons-wrapper';

            const editBtn = document.createElement('button');
            editBtn.className = 'action-btn';
            editBtn.title = '编辑';
            editBtn.textContent = '✏️';
            editBtn.addEventListener('click', () => handleAction('edit', anime.animeId, anime.title));
            wrapper.appendChild(editBtn);

            const viewBtn = document.createElement('button');
            viewBtn.className = 'action-btn';
            viewBtn.title = '查看数据源';
            viewBtn.textContent = '📖';
            viewBtn.addEventListener('click', () => handleAction('view', anime.animeId, anime.title));
            wrapper.appendChild(viewBtn);

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'action-btn';
            deleteBtn.title = '删除';
            deleteBtn.textContent = '🗑️';
            deleteBtn.addEventListener('click', () => handleAction('delete', anime.animeId, anime.title));
            wrapper.appendChild(deleteBtn);

            actionsCell.appendChild(wrapper);
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

    async function showAnimeDetailView(animeId) {
        // 1. Switch views and show loading state
        libraryView.classList.add('hidden');
        editAnimeView.classList.add('hidden');
        episodeListView.classList.add('hidden');
        danmakuListView.classList.add('hidden');
        animeDetailView.classList.remove('hidden');
        
        // Clear previous content
        detailViewTitle.textContent = '加载中...';
        detailViewMeta.textContent = '';
        detailViewImg.src = '/static/placeholder.png';
        sourceDetailTableBody.innerHTML = '';
    
        try {
            // 2. Fetch data
            const [fullLibrary, sources] = await Promise.all([
                apiFetch('/api/ui/library'),
                apiFetch(`/api/ui/library/anime/${animeId}/sources`)
            ]);
    
            const anime = fullLibrary.animes.find(a => a.animeId === animeId);
            if (!anime) throw new Error("找不到该作品的信息。");
    
            // 3. Populate the static template in index.html
            detailViewImg.src = anime.imageUrl || '/static/placeholder.png';
            detailViewImg.alt = anime.title;
            detailViewTitle.textContent = anime.title;
            detailViewMeta.textContent = `季: ${anime.season} | 总集数: ${anime.episodeCount || 0} | 已关联 ${sources.length} 个源`;
    
            if (sources.length > 0) {
                sources.forEach(source => {
                    const row = sourceDetailTableBody.insertRow();
                    row.insertCell().textContent = source.provider_name;
                    row.insertCell().textContent = source.media_id;
                    const statusCell = row.insertCell();
                    statusCell.textContent = source.is_favorited ? '🌟' : '';
                    row.insertCell().textContent = new Date(source.created_at).toLocaleString();
                    const actionsCell = row.insertCell();
                    actionsCell.className = 'actions-cell';

                    const wrapper = document.createElement('div');
                    wrapper.className = 'action-buttons-wrapper';

                    const favoriteBtn = document.createElement('button');
                    favoriteBtn.className = 'action-btn';
                    favoriteBtn.title = '精确标记';
                    favoriteBtn.textContent = source.is_favorited ? '🌟' : '⭐';
                    favoriteBtn.addEventListener('click', () => handleSourceAction('favorite', source.source_id, anime.title, anime.animeId));
                    wrapper.appendChild(favoriteBtn);

                    const viewEpisodesBtn = document.createElement('button');
                    viewEpisodesBtn.className = 'action-btn';
                    viewEpisodesBtn.title = '查看/编辑分集';
                    viewEpisodesBtn.textContent = '📖';
                    viewEpisodesBtn.addEventListener('click', () => handleSourceAction('view_episodes', source.source_id, anime.title, anime.animeId));
                    wrapper.appendChild(viewEpisodesBtn);

                    const refreshBtn = document.createElement('button');
                    refreshBtn.className = 'action-btn';
                    refreshBtn.title = '刷新此源';
                    refreshBtn.textContent = '🔄';
                    refreshBtn.addEventListener('click', () => handleSourceAction('refresh', source.source_id, anime.title, anime.animeId));
                    wrapper.appendChild(refreshBtn);

                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'action-btn';
                    deleteBtn.title = '删除此源';
                    deleteBtn.textContent = '🗑️';
                    deleteBtn.addEventListener('click', () => handleSourceAction('delete', source.source_id, anime.title, anime.animeId));
                    wrapper.appendChild(deleteBtn);

                    actionsCell.appendChild(wrapper);
                });
            } else {
                sourceDetailTableBody.innerHTML = `<tr><td colspan="5">未关联任何数据源。</td></tr>`;
            }
        } catch (error) {
            detailViewTitle.textContent = '加载详情失败';
            detailViewMeta.textContent = error.message || error;
        }
    }

    function handleSearchBgmId() {
        const title = document.getElementById('edit-anime-title').value;
        const animeId = document.getElementById('edit-anime-id').value;
    
        // Store context
        bangumiSearchView.dataset.returnToAnimeId = animeId;
    
        // Switch views
        editAnimeView.classList.add('hidden');
        bangumiSearchView.classList.remove('hidden');
    
        // Pre-populate search
        bangumiSearchKeywordInput.value = title;
        bangumiSearchViewTitle.textContent = `为 "${title}" 搜索 Bangumi ID`;
        bangumiSearchResultsList.innerHTML = ''; // Clear previous results
    }
    
    function handleBackToEditAnime() {
        bangumiSearchView.classList.add('hidden');
        editAnimeView.classList.remove('hidden');
    }
    
    async function handleBangumiSearchSubmit(e) {
        e.preventDefault();
        const keyword = bangumiSearchKeywordInput.value.trim();
        if (!keyword) return;
    
        bangumiSearchResultsList.innerHTML = '<li>正在搜索...</li>';
        const searchButton = bangumiSearchForm.querySelector('button[type="submit"]');
        searchButton.disabled = true;
    
        try {
            const results = await apiFetch(`/api/bgm/search?keyword=${encodeURIComponent(keyword)}`);
            renderBangumiSearchResults(results);
        } catch (error) {
            bangumiSearchResultsList.innerHTML = `<li class="error">搜索失败: ${error.message}</li>`;
        } finally {
            searchButton.disabled = false;
        }
    }
    
    function renderBangumiSearchResults(results) {
        bangumiSearchResultsList.innerHTML = '';
        if (results.length === 0) {
            bangumiSearchResultsList.innerHTML = '<li>未找到匹配项。</li>';
            return;
        }
    
        results.forEach(result => {
            const li = document.createElement('li');
            
            // 创建左侧容器 (海报 + 信息)
            const leftContainer = document.createElement('div');
            leftContainer.className = 'result-item-left';

            // 创建并添加海报图片
            const posterImg = document.createElement('img');
            posterImg.className = 'poster';
            posterImg.src = result.image_url || '/static/placeholder.png';
            posterImg.referrerPolicy = 'no-referrer';
            posterImg.alt = result.name;
            leftContainer.appendChild(posterImg);

            // 创建信息div
            const infoDiv = document.createElement('div');
            infoDiv.className = 'info';
            const detailsText = result.details ? `${result.details} / ID: ${result.id}` : `ID: ${result.id}`;
            infoDiv.innerHTML = `<p class="title">${result.name}</p><p class="meta">${detailsText}</p>`;
            leftContainer.appendChild(infoDiv);

            li.appendChild(leftContainer);

            // 创建选择按钮
            const selectBtn = document.createElement('button');
            selectBtn.textContent = '选择';
            selectBtn.addEventListener('click', () => {
                _currentSearchSelectionData = result; // 存储完整结果
                handleBackToEditAnime(); // 返回编辑视图
                // 延迟应用，确保视图已切换
                setTimeout(applySearchSelectionData, 50);
            });
            li.appendChild(selectBtn);

            bangumiSearchResultsList.appendChild(li);
        });
    }

    function handleSearchTmdbId() {
        const title = document.getElementById('edit-anime-title').value;
        const animeId = document.getElementById('edit-anime-id').value;

        // Store context
        tmdbSearchView.dataset.returnToAnimeId = animeId;

        // Switch views
        editAnimeView.classList.add('hidden');
        tmdbSearchView.classList.remove('hidden');

        // Pre-populate search
        document.getElementById('tmdb-search-keyword').value = title;
        document.getElementById('tmdb-search-view-title').textContent = `为 "${title}" 搜索 TMDB ID`;
        tmdbSearchResultsList.innerHTML = ''; // Clear previous results
    }

    async function handleTmdbSearchSubmit(e) {
        e.preventDefault();
        const keyword = document.getElementById('tmdb-search-keyword').value.trim();
        if (!keyword) return;

        tmdbSearchResultsList.innerHTML = '<li>正在搜索...</li>';
        const searchButton = tmdbSearchForm.querySelector('button[type="submit"]');
        searchButton.disabled = true;

        try {
            // Determine media type from the edit form
            const mediaType = document.getElementById('edit-anime-type').value;
            const searchUrl = mediaType === 'movie' ? '/api/tmdb/search/movie' : '/api/tmdb/search/tv';
            
            const results = await apiFetch(`${searchUrl}?keyword=${encodeURIComponent(keyword)}`);
            renderTmdbSearchResults(results);
        } catch (error) {
            tmdbSearchResultsList.innerHTML = `<li class="error">搜索失败: ${error.message}</li>`;
        } finally {
            searchButton.disabled = false;
        }
    }

    function renderTmdbSearchResults(results) {
        tmdbSearchResultsList.innerHTML = '';
        if (results.length === 0) {
            tmdbSearchResultsList.innerHTML = '<li>未找到匹配项。</li>';
            return;
        }

        results.forEach(result => {
            const li = document.createElement('li');
            
            const leftContainer = document.createElement('div');
            leftContainer.className = 'result-item-left';

            const posterImg = document.createElement('img');
            posterImg.className = 'poster';
            posterImg.src = result.image_url || '/static/placeholder.png';
            posterImg.referrerPolicy = 'no-referrer';
            posterImg.alt = result.name;
            leftContainer.appendChild(posterImg);

            const infoDiv = document.createElement('div');
            infoDiv.className = 'info';
            infoDiv.innerHTML = `<p class="title">${result.name}</p><p class="meta">ID: ${result.id}</p>`;
            leftContainer.appendChild(infoDiv);

            li.appendChild(leftContainer);

            const selectBtn = document.createElement('button');
            selectBtn.textContent = '选择';
            selectBtn.addEventListener('click', async () => {
                const mediaType = document.getElementById('edit-anime-type').value === 'movie' ? 'movie' : 'tv';
                try {
                    const details = await apiFetch(`/api/tmdb/details/${mediaType}/${result.id}`);
                    _currentSearchSelectionData = details;
                    handleBackToEditAnime();
                    setTimeout(applySearchSelectionData, 50);
                } catch (error) {
                    alert(`获取TMDB详情失败: ${error.message}`);
                }
            });
            li.appendChild(selectBtn);

            tmdbSearchResultsList.appendChild(li);
        });
    }

    async function showEditAnimeView(animeId) {
        libraryView.classList.add('hidden');
        animeDetailView.classList.add('hidden');
        // 新增：在显示编辑视图前，清除旧的搜索选择状态
        clearSearchSelectionState();
        episodeListView.classList.add('hidden');
        editAnimeView.classList.remove('hidden');
        
        // Clear form and show loading state
        editAnimeForm.reset();
        editAnimeForm.querySelector('button[type="submit"]').disabled = true;

        try {
            const details = await apiFetch(`/api/ui/library/anime/${animeId}/details`);
            
            // Populate form
            document.getElementById('edit-anime-id').value = details.anime_id;
            document.getElementById('edit-anime-title').value = details.title;
            editAnimeTypeSelect.value = details.type;
            document.getElementById('edit-anime-season').value = details.season;
            document.getElementById('edit-anime-tmdbid').value = details.tmdb_id || '';
            document.getElementById('edit-anime-egid').value = details.tmdb_episode_group_id || '';
            document.getElementById('edit-anime-bgmid').value = details.bangumi_id || '';
            document.getElementById('edit-anime-tvdbid').value = details.tvdb_id || '';
            document.getElementById('edit-anime-doubanid').value = details.douban_id || '';
            document.getElementById('edit-anime-imdbid').value = details.imdb_id || '';
            document.getElementById('edit-anime-name-en').value = details.name_en || '';
            document.getElementById('edit-anime-name-jp').value = details.name_jp || '';
            document.getElementById('edit-anime-name-romaji').value = details.name_romaji || '';
            document.getElementById('edit-anime-alias-cn-1').value = details.alias_cn_1 || '';
            document.getElementById('edit-anime-alias-cn-2').value = details.alias_cn_2 || '';
            document.getElementById('edit-anime-alias-cn-3').value = details.alias_cn_3 || '';
            // Trigger change handler to set initial state of season input
            handleAnimeTypeChange();
            updateEgidButtonStates();

        } catch (error) {
            alert(`加载编辑信息失败: ${error.message}`);
            document.getElementById('back-to-library-from-edit-btn').click();
        } finally {
            editAnimeForm.querySelector('button[type="submit"]').disabled = false;
        }
    }

    function clearSearchSelectionState() {
        _currentSearchSelectionData = null;
        const applyBtns = document.querySelectorAll('#edit-anime-form .apply-btn');
        applyBtns.forEach(btn => btn.remove()); // 直接从DOM中移除所有“应用”按钮
    }

    function applySearchSelectionData() {
        if (!_currentSearchSelectionData) return;
        const data = _currentSearchSelectionData;

        // Check if it's a Bangumi or TMDB result by looking for a unique key
        if ('details' in data) { // Bangumi result
            document.getElementById('edit-anime-bgmid').value = data.id || '';
            updateFieldWithApplyLogic('edit-anime-name-jp', data.name_jp);
            updateFieldWithApplyLogic('edit-anime-name-en', data.name_en);
            updateFieldWithApplyLogic('edit-anime-name-romaji', data.name_romaji);

            const cnAliases = data.aliases_cn || [];
            updateFieldWithApplyLogic('edit-anime-alias-cn-1', cnAliases[0]);
            updateFieldWithApplyLogic('edit-anime-alias-cn-2', cnAliases[1]);
            updateFieldWithApplyLogic('edit-anime-alias-cn-3', cnAliases[2]);
        } else { // Assume TMDB result
            document.getElementById('edit-anime-tmdbid').value = data.id || '';
            updateFieldWithApplyLogic('edit-anime-imdbid', data.imdb_id);
            updateFieldWithApplyLogic('edit-anime-tvdbid', data.tvdb_id);
            updateFieldWithApplyLogic('edit-anime-name-en', data.name_en);
            updateFieldWithApplyLogic('edit-anime-name-jp', data.name_jp);
            updateFieldWithApplyLogic('edit-anime-name-romaji', data.name_romaji);
            const cnAliases = data.aliases_cn || [];
            updateFieldWithApplyLogic('edit-anime-alias-cn-1', cnAliases[0]);
            updateFieldWithApplyLogic('edit-anime-alias-cn-2', cnAliases[1]);
            updateFieldWithApplyLogic('edit-anime-alias-cn-3', cnAliases[2]);
        }
    }

    function updateFieldWithApplyLogic(fieldId, newValue) {
        const input = document.getElementById(fieldId);
        if (!input) return;

        const wrapper = input.parentElement;
        let applyBtn = wrapper.querySelector('.apply-btn');
        const normalizedNewValue = (newValue === null || newValue === undefined) ? '' : String(newValue).trim();

        if (normalizedNewValue === '') {
            if (applyBtn) applyBtn.remove(); // 如果新值为空，移除按钮
            return;
        }

        const currentValue = input.value.trim();
        if (currentValue === '' || currentValue === normalizedNewValue) {
            input.value = normalizedNewValue;
            if (applyBtn) applyBtn.remove(); // 如果值匹配或原值为空，更新并移除按钮
        } else { // 如果值不匹配，则创建或更新按钮
            if (!applyBtn) {
                applyBtn = document.createElement('button');
                applyBtn.type = 'button';
                applyBtn.className = 'apply-btn';
                applyBtn.title = '应用搜索结果';
                applyBtn.textContent = '↵';
                wrapper.appendChild(applyBtn);
            }
            applyBtn.dataset.newValue = normalizedNewValue;
        }
    }

    function handleBackToEditAnime() {
        bangumiSearchView.classList.add('hidden');
        tmdbSearchView.classList.add('hidden');
        editAnimeView.classList.remove('hidden');
    }
    
    async function handleSelectEgidClick() {
        const tmdbId = document.getElementById('edit-anime-tmdbid').value.trim();
        if (!tmdbId) return;

        egidSelectionList.innerHTML = '<li>正在加载...</li>';
        egidSelectionModal.classList.remove('hidden');

        try {
            const groups = await apiFetch(`/api/tmdb/tv/${tmdbId}/episode_groups`);
            renderEgidSelectionModal(groups);
        } catch (error) {
            egidSelectionList.innerHTML = `<li class="error">加载剧集组失败: ${error.message}</li>`;
        }
    }

    function renderEgidSelectionModal(groups) {
        egidSelectionList.innerHTML = '';
        if (groups.length === 0) {
            egidSelectionList.innerHTML = '<li>未找到任何剧集组。</li>';
            return;
        }
        groups.forEach(group => {
            const li = document.createElement('li');
            li.dataset.groupId = group.id;
            li.style.cursor = 'pointer';
            li.innerHTML = `
                <div class="info">
                    <p class="title">${group.name}</p>
                    <p class="meta">${group.description || '无描述'} (${group.group_count} 组, ${group.episode_count} 集)</p>
                </div>
            `;
            egidSelectionList.appendChild(li);
        });
    }

    function handleEgidSelection(e) {
        const li = e.target.closest('li');
        if (li && li.dataset.groupId) {
            document.getElementById('edit-anime-egid').value = li.dataset.groupId;
            egidSelectionModal.classList.add('hidden');
            updateEgidButtonStates(); // Update view button state
        }
    }

    async function handleViewEgidEpisodesClick() {
        const groupId = document.getElementById('edit-anime-egid').value.trim();
        if (!groupId) return;

        egidEpisodesListContainer.innerHTML = '<p>正在加载剧集详情...</p>';
        egidEpisodesModal.classList.remove('hidden');

        try {
            const details = await apiFetch(`/api/tmdb/episode_group/${groupId}`);
            egidEpisodesModalTitle.textContent = `剧集详情: ${details.name}`;
            renderEgidEpisodesModal(details.groups);
        } catch (error) {
            egidEpisodesListContainer.innerHTML = `<p class="error">加载剧集详情失败: ${error.message}</p>`;
        }
    }

    function renderEgidEpisodesModal(groups) {
        egidEpisodesListContainer.innerHTML = '';
        groups.forEach(group => {
            const groupDiv = document.createElement('div');
            groupDiv.className = 'egid-season-group';
            let episodesHtml = group.episodes.map(ep => `<li>S${ep.season_number}E${ep.episode_number}: ${ep.name}</li>`).join('');
            groupDiv.innerHTML = `<h4>${group.name} (Order: ${group.order})</h4><ul>${episodesHtml}</ul>`;
            egidEpisodesListContainer.appendChild(groupDiv);
        });
    }

    // --- Episode List View ---
    async function showEpisodeListView(sourceId, animeTitle, animeId) {
        animeDetailView.classList.add('hidden');
        editEpisodeView.classList.add('hidden');
        episodeListView.classList.remove('hidden');
        episodeListView.innerHTML = '<div>加载中...</div>';

        try {
            const episodes = await apiFetch(`/api/ui/library/source/${sourceId}/episodes`);
            currentEpisodes = episodes; // 存储分集列表上下文
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

                const wrapper = document.createElement('div');
                wrapper.className = 'action-buttons-wrapper';

                const editBtn = document.createElement('button');
                editBtn.className = 'action-btn';
                editBtn.title = '编辑剧集';
                editBtn.textContent = '✏️';
                editBtn.addEventListener('click', () => handleEpisodeAction('edit', ep.id, ep.title));
                wrapper.appendChild(editBtn);

                const refreshBtn = document.createElement('button');
                refreshBtn.className = 'action-btn';
                refreshBtn.title = '刷新剧集';
                refreshBtn.textContent = '🔄';
                refreshBtn.addEventListener('click', () => handleEpisodeAction('refresh', ep.id, ep.title));
                wrapper.appendChild(refreshBtn);

                const viewDanmakuBtn = document.createElement('button');
                viewDanmakuBtn.className = 'action-btn';
                viewDanmakuBtn.title = '查看具体弹幕';
                viewDanmakuBtn.textContent = '💬';
                viewDanmakuBtn.addEventListener('click', () => handleEpisodeAction('view_danmaku', ep.id, ep.title));
                wrapper.appendChild(viewDanmakuBtn);

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'action-btn';
                deleteBtn.title = '删除集';
                deleteBtn.textContent = '🗑️';
                deleteBtn.addEventListener('click', () => handleEpisodeAction('delete', ep.id, ep.title));
                wrapper.appendChild(deleteBtn);

                actionsCell.appendChild(wrapper);
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

            const wrapper = document.createElement('div');
            wrapper.className = 'action-buttons-wrapper';

            const copyBtn = document.createElement('button');
            copyBtn.className = 'action-btn';
            copyBtn.title = '复制链接';
            copyBtn.textContent = '📋';
            copyBtn.addEventListener('click', () => handleTokenAction('copy', token.id, token.token));
            wrapper.appendChild(copyBtn);

            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'action-btn';
            toggleBtn.title = enabledText;
            toggleBtn.textContent = token.is_enabled ? '⏸️' : '▶️';
            toggleBtn.addEventListener('click', () => handleTokenAction('toggle', token.id));
            wrapper.appendChild(toggleBtn);

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'action-btn';
            deleteBtn.title = '删除';
            deleteBtn.textContent = '🗑️';
            deleteBtn.addEventListener('click', () => handleTokenAction('delete', token.id));
            wrapper.appendChild(deleteBtn);

            actionsCell.appendChild(wrapper);
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
    window.handleAction = (action, animeId, title) => {

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
            showEditAnimeView(animeId);
        } else if (action === 'view') {
            showAnimeDetailView(animeId);
        } else {
            alert(`功能 '${action}' 尚未实现。`);
        }
    };

    window.handleEpisodeAction = (action, episodeId, title) => {
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
                    showEpisodeListView(sourceId, animeTitle, animeId);
                }).catch(error => {
                    alert(`删除失败: ${(error.message || error)}`);
                });
            }
        } else if (action === 'edit') {
            const episode = currentEpisodes.find(ep => ep.id === episodeId);
            if (!episode) {
                alert('错误：在当前上下文中找不到该分集的信息。');
                return;
            }
            const episodeIndex = episode.episode_index;
            const sourceUrl = episode.source_url;
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

    window.handleSourceAction = (action, sourceId, title, animeId) => {
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

    function handleSettingsSubNav(e) {
        const subNavBtn = e.target.closest('.sub-nav-btn');
        if (!subNavBtn) return;

        const subViewId = subNavBtn.getAttribute('data-subview');
        if (!subViewId) return;

        // Update button active state
        settingsSubNav.querySelectorAll('.sub-nav-btn').forEach(btn => btn.classList.remove('active'));
        subNavBtn.classList.add('active');

        // Update view visibility
        settingsSubViews.forEach(view => view.classList.add('hidden'));
        const targetSubView = document.getElementById(subViewId);
        if (targetSubView) {
            targetSubView.classList.remove('hidden');
        }

        // 当切换到 Bangumi 配置子视图时，加载其授权状态
        if (subViewId === 'bangumi-settings-subview') {
            loadBangumiAuthState();
        }
        if (subViewId === 'tmdb-settings-subview') {
            loadTmdbSettings();
        }
    }

    async function loadTmdbSettings() {
        const apiKeyInput = document.getElementById('tmdb-api-key');
        const apiBaseUrlInput = document.getElementById('tmdb-api-base-url');
        const imageBaseUrlInput = document.getElementById('tmdb-image-base-url');
        const messageEl = document.getElementById('tmdb-save-message');
        messageEl.textContent = '';
        try {
            const data = await apiFetch('/api/ui/config/tmdb');
            apiKeyInput.value = data.tmdb_api_key || '';
            apiBaseUrlInput.value = data.tmdb_api_base_url || '';
            imageBaseUrlInput.value = data.tmdb_image_base_url || '';
        } catch (error) {
            messageEl.textContent = `加载TMDB配置失败: ${error.message}`;
        }
    }

    async function loadBangumiAuthState() {
        try {
            const state = await apiFetch('/api/bgm/auth/state');
            if (state.is_authenticated) {
                bangumiUserNickname.textContent = state.nickname;
                bangumiUserId.textContent = state.bangumi_user_id || 'N/A';
                bangumiAuthorizedAt.textContent = state.authorized_at ? new Date(state.authorized_at).toLocaleString() : 'N/A';
                bangumiExpiresAt.textContent = state.expires_at ? new Date(state.expires_at).toLocaleString() : '永不（或未知）';
                bangumiUserAvatar.src = state.avatar_url || '/static/placeholder.png';

                bangumiAuthStateAuthenticated.classList.remove('hidden');
                bangumiAuthStateUnauthenticated.classList.add('hidden');
                bangumiLoginBtn.classList.add('hidden');
                bangumiLogoutBtn.classList.remove('hidden');
            } else {
                bangumiAuthStateAuthenticated.classList.add('hidden');
                bangumiAuthStateUnauthenticated.classList.remove('hidden');
                bangumiLoginBtn.classList.remove('hidden');
                bangumiLogoutBtn.classList.add('hidden');
            }
        } catch (error) {
            bangumiAuthStateUnauthenticated.innerHTML = `<p class="error">获取授权状态失败: ${error.message}</p>`;
            bangumiAuthStateAuthenticated.classList.add('hidden');
            bangumiAuthStateUnauthenticated.classList.remove('hidden');
        }
    }

    // --- Initial Load ---
    setupEventListeners();
    checkLogin();
});
