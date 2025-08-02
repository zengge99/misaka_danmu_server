import { apiFetch } from '../api.js';
import { toggleLoader } from '../ui.js';

let logRefreshInterval = null;
let originalSearchResults = [];

function setupEventListeners() {
    document.getElementById('search-form').addEventListener('submit', handleSearch);
    document.getElementById('test-match-form').addEventListener('submit', handleTestMatch);
    document.getElementById('clear-cache-btn').addEventListener('click', handleClearCache);
    document.getElementById('bulk-import-btn').addEventListener('click', handleBulkImport);
    document.getElementById('select-all-btn').addEventListener('click', handleSelectAll);
    document.getElementById('filter-btn-movie').addEventListener('click', handleTypeFilterClick);
    document.getElementById('filter-btn-tv_series').addEventListener('click', handleTypeFilterClick);
    document.getElementById('results-filter-input').addEventListener('input', applyFiltersAndRender);

    // Listen to global events
    document.addEventListener('logrefresh:start', startLogRefresh);
    document.addEventListener('logrefresh:stop', stopLogRefresh);
}

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
    const logOutput = document.getElementById('log-output');
    if (!localStorage.getItem('danmu_api_token') || !logOutput) return;
    try {
        const logs = await apiFetch('/api/ui/logs');
        logOutput.textContent = logs.join('\n');
    } catch (error) {
        console.error("刷新日志失败:", error.message);
    }
}

async function handleSearch(e) {
    e.preventDefault();
    const keyword = document.getElementById('search-keyword').value;
    if (!keyword) return;

    document.getElementById('results-list').innerHTML = '';
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

function displayResults(results) {
    originalSearchResults = results;
    const resultsFilterControls = document.getElementById('results-filter-controls');
    resultsFilterControls.classList.toggle('hidden', results.length === 0);

    if (results.length > 0) {
        document.getElementById('filter-btn-movie').classList.add('active');
        document.getElementById('filter-btn-movie').querySelector('.status-icon').textContent = '✅';
        document.getElementById('filter-btn-tv_series').classList.add('active');
        document.getElementById('filter-btn-tv_series').querySelector('.status-icon').textContent = '✅';
        document.getElementById('results-filter-input').value = '';
        applyFiltersAndRender();
    } else {
        document.getElementById('results-list').innerHTML = '<li>未找到结果。</li>';
    }
}

function applyFiltersAndRender() {
    if (!originalSearchResults) return;
    const activeTypes = new Set();
    if (document.getElementById('filter-btn-movie').classList.contains('active')) activeTypes.add('movie');
    if (document.getElementById('filter-btn-tv_series').classList.contains('active')) activeTypes.add('tv_series');
    let filteredResults = originalSearchResults.filter(item => activeTypes.has(item.type));
    const filterText = document.getElementById('results-filter-input').value.toLowerCase();
    if (filterText) {
        filteredResults = filteredResults.filter(item => item.title.toLowerCase().includes(filterText));
    }
    renderSearchResults(filteredResults);
}

function renderSearchResults(results) {
    const resultsList = document.getElementById('results-list');
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
        
        // Add click listener to the entire row (li)
        li.addEventListener('click', (e) => {
            // Only toggle if the click is not on the button or the checkbox itself
            if (e.target.tagName !== 'BUTTON' && e.target.tagName !== 'INPUT') {
                checkbox.checked = !checkbox.checked;
            }
        });

        const posterImg = document.createElement('img');
        posterImg.className = 'poster';
        posterImg.src = item.imageUrl || '/static/placeholder.png';
        posterImg.referrerPolicy = 'no-referrer';
        posterImg.alt = item.title;
        leftContainer.appendChild(posterImg);
        const infoDiv = document.createElement('div');
        infoDiv.className = 'info';
        infoDiv.innerHTML = `<p class="title">${item.title}</p><p class="meta">源: ${item.provider} | 类型: ${item.type} | 年份: ${item.year || 'N/A'}</p>`;
        leftContainer.appendChild(infoDiv);
        const importBtn = document.createElement('button');
        importBtn.textContent = '导入弹幕';
        li.appendChild(leftContainer);
        importBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent the li click event from firing
            handleImportClick(importBtn, item)
        });
        li.appendChild(importBtn);
        resultsList.appendChild(li);
    });
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

async function handleTestMatch(e) {
    e.preventDefault();
    const apiToken = document.getElementById('test-token-input').value.trim();
    const filename = document.getElementById('test-filename-input').value.trim();
    if (!apiToken || !filename) {
        alert('Token和文件名都不能为空。');
        return;
    }
    const testMatchResults = document.getElementById('test-match-results');
    testMatchResults.textContent = '正在测试...';
    const testButton = e.target.querySelector('button');
    testButton.disabled = true;

    try {
        const data = await apiFetch(`/api/${apiToken}/match`, {
            method: 'POST',
            body: JSON.stringify({ fileName: filename })
        });
        if (data.isMatched) {
            const match = data.matches[0];
            testMatchResults.textContent = `[匹配成功]\n番剧: ${match.animeTitle} (ID: ${match.animeId})\n分集: ${match.episodeTitle} (ID: ${match.episodeId})\n类型: ${match.typeDescription}`;
        } else {
            testMatchResults.textContent = '未匹配到任何结果。';
        }
    } catch (error) {
        testMatchResults.textContent = `请求失败: ${(error.message || error)}`;
    } finally {
        testButton.disabled = false;
    }
}

async function handleClearCache() {
    if (confirm("您确定要清除所有缓存吗？\n这将清除所有搜索结果和分集列表的临时缓存，下次访问时需要重新从网络获取。")) {
        try {
            const response = await apiFetch('/api/ui/cache/clear', { method: 'POST' });
            alert(response.message || "缓存已成功清除！");
        } catch (error) {
            alert(`清除缓存失败: ${(error.message || error)}`);
        }
    }
}

async function handleBulkImport() {
    const resultsList = document.getElementById('results-list');
    const selectedCheckboxes = resultsList.querySelectorAll('input[type="checkbox"]:checked');
    const selectedMediaIds = new Set(Array.from(selectedCheckboxes).map(checkbox => checkbox.value));

    if (selectedMediaIds.size === 0) {
        alert("请选择要导入的媒体。");
        return;
    }

    if (!confirm(`确定要批量导入 ${selectedMediaIds.size} 个媒体吗？`)) return;
    
    const bulkImportBtn = document.getElementById('bulk-import-btn');
    bulkImportBtn.disabled = true;
    bulkImportBtn.textContent = '批量导入中...';

    const itemsToImport = originalSearchResults.filter(item => selectedMediaIds.has(item.mediaId));

    try {
        for (const item of itemsToImport) {
            try {
                const data = await apiFetch('/api/ui/import', {
                    method: 'POST',
                    body: JSON.stringify({
                        provider: item.provider, media_id: item.mediaId, anime_title: item.title,
                        type: item.type, image_url: item.imageUrl, douban_id: item.douban_id,
                        current_episode_index: item.currentEpisodeIndex,
                    }),
                });
                console.log(`提交导入任务 ${item.title} 成功: ${data.message}`);
            } catch (error) {
                console.error(`提交导入任务 ${item.title} 失败: ${error.message || error}`);
            }
            await new Promise(resolve => setTimeout(resolve, 200));
        }
        alert("批量导入任务已提交，请在任务管理器中查看进度。");
    } finally {
        bulkImportBtn.disabled = false;
        bulkImportBtn.textContent = '批量导入';
    }
}

function handleSelectAll() {
    const resultsList = document.getElementById('results-list');
    const checkboxes = resultsList.querySelectorAll('input[type="checkbox"]');
    if (checkboxes.length === 0) return;
    const shouldCheckAll = Array.from(checkboxes).some(cb => !cb.checked);
    checkboxes.forEach(cb => { cb.checked = shouldCheckAll; });
}

function handleTypeFilterClick(e) {
    const btn = e.currentTarget;
    btn.classList.toggle('active');
    const icon = btn.querySelector('.status-icon');
    icon.textContent = btn.classList.contains('active') ? '✅' : '❌';
    applyFiltersAndRender();
}

export { setupEventListeners as setupHomeEventListeners };
