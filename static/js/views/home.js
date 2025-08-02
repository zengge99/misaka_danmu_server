import { apiFetch } from '../api.js';
import { toggleLoader, switchView } from '../ui.js';

let logRefreshInterval = null;
let originalSearchResults = [];
let itemsForBulkImport = [];

function setupEventListeners() {
    // Home View
    document.getElementById('search-form').addEventListener('submit', handleSearch);
    document.getElementById('test-match-form').addEventListener('submit', handleTestMatch);
    document.getElementById('clear-cache-btn').addEventListener('click', handleClearCache);
    document.getElementById('bulk-import-btn').addEventListener('click', handleBulkImport);
    document.getElementById('select-all-btn').addEventListener('click', handleSelectAll);
    document.getElementById('filter-btn-movie').addEventListener('click', handleTypeFilterClick);
    document.getElementById('filter-btn-tv_series').addEventListener('click', handleTypeFilterClick);
    document.getElementById('results-filter-input').addEventListener('input', applyFiltersAndRender);

    // Bulk Import View
    document.getElementById('cancel-bulk-import-btn').addEventListener('click', () => switchView('home-view'));
    document.getElementById('confirm-bulk-import-btn').addEventListener('click', handleConfirmBulkImport);
    document.getElementById('search-tmdb-for-bulk-btn').addEventListener('click', handleBulkTmdbSearch);

    // Listen to global events
    document.addEventListener('logrefresh:start', startLogRefresh);
    document.addEventListener('logrefresh:stop', stopLogRefresh);
    document.addEventListener('tmdb-search:selected-for-bulk', (e) => {
        // Listen for the event dispatched from editAnime.js
        const chineseName = e.detail.aliases_cn && e.detail.aliases_cn.length > 0 ? e.detail.aliases_cn[0] : null;
        document.getElementById('final-import-name').value = chineseName || e.detail.name_en || e.detail.name_jp || '';
        document.getElementById('final-import-tmdb-id').value = e.detail.id || '';
        switchView('bulk-import-view'); // Switch back to the bulk import view
    });
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
        const processedResults = data.results.map(item => ({
            ...item,
            season: parseTitleForSeason(item.title)
        }));
        displayResults(processedResults);
    } catch (error) {
        alert(`搜索失败: ${(error.message || error)}`);
    } finally {
        toggleLoader(false);
    }
}

function parseTitleForSeason(title) {
    if (!title) return 1;

    const patterns = [
        /(?:S|Season)\s*(\d+)/i,
        /第\s*([一二三四五六七八九十\d]+)\s*[季部]/,
        /第\s*([一二三四五六七八九十\d]+)\s*(?:部分|篇|章|幕)/,
    ];

    const chineseNumMap = { '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10 };

    for (const pattern of patterns) {
        const match = title.match(pattern);
        if (match && match[1]) {
            const numStr = match[1];
            if (numStr.match(/^\d+$/)) {
                return parseInt(numStr, 10);
            } else if (chineseNumMap[numStr]) {
                return chineseNumMap[numStr];
            }
        }
    }
    return 1; // Default to season 1
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
                season: item.season, // Pass detected season
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
    if (selectedCheckboxes.length === 0) {
        alert("请选择要导入的媒体。");
        return;
    }

    const selectedMediaIds = new Set(Array.from(selectedCheckboxes).map(cb => cb.value));
    itemsForBulkImport = originalSearchResults.filter(item => selectedMediaIds.has(item.mediaId));

    const uniqueTitles = new Set(itemsForBulkImport.map(item => item.title));

    if (uniqueTitles.size === 1) {
        // All titles are the same, import directly
        if (confirm(`确定要将 ${itemsForBulkImport.length} 个条目作为同一作品 "${itemsForBulkImport[0].title}" 导入吗？`)) {
            _performDirectBulkImport(itemsForBulkImport, itemsForBulkImport[0].title);
        }
    } else {
        // Titles are different, show confirmation view
        _showBulkImportView(itemsForBulkImport);
    }
}

function _showBulkImportView(items) {
    switchView('bulk-import-view');
    const listEl = document.getElementById('bulk-import-list');
    listEl.innerHTML = '';
    items.forEach(item => {
        const li = document.createElement('li');
        li.textContent = `${item.title} (源: ${item.provider}, 类型: ${item.type}, 季: ${item.season})`;
        li.style.cursor = 'pointer';
        li.addEventListener('click', () => {
            document.getElementById('final-import-name').value = item.title;
        });
        listEl.appendChild(li);
    });
    // Set the first item's title as the default
    document.getElementById('final-import-name').value = items[0].title;
    document.getElementById('final-import-tmdb-id').value = '';
}

async function _performDirectBulkImport(items, finalTitle, finalTmdbId = null) {
    const bulkImportBtn = document.getElementById('bulk-import-btn');
    bulkImportBtn.disabled = true;
    bulkImportBtn.textContent = '批量导入中...';

    try {
        for (const item of items) {
            try {
                const data = await apiFetch('/api/ui/import', {
                    method: 'POST',
                    body: JSON.stringify({
                        provider: item.provider, media_id: item.mediaId, anime_title: item.title,
                        type: item.type, season: item.season, image_url: item.imageUrl, douban_id: item.douban_id,
                        current_episode_index: item.currentEpisodeIndex,
                        tmdb_id: finalTmdbId // Pass the final TMDB ID
                    }),
                });
                console.log(`提交导入任务 ${finalTitle} (源: ${item.provider}) 成功: ${data.message}`);
            } catch (error) {
                console.error(`提交导入任务 ${finalTitle} (源: ${item.provider}) 失败: ${error.message || error}`);
            }
            await new Promise(resolve => setTimeout(resolve, 200));
        }
        alert("批量导入任务已提交，请在任务管理器中查看进度。");
    } finally {
        bulkImportBtn.disabled = false;
        bulkImportBtn.textContent = '批量导入';
        switchView('home-view'); // Go back to home view after completion
    }
}

function handleConfirmBulkImport() {
    const finalTitle = document.getElementById('final-import-name').value.trim();
    const finalTmdbId = document.getElementById('final-import-tmdb-id').value.trim() || null;
    if (!finalTitle) {
        alert("最终导入名称不能为空。");
        return;
    }
    if (itemsForBulkImport.length > 0) {
        _performDirectBulkImport(itemsForBulkImport, finalTitle, finalTmdbId);
    }
}

function handleBulkTmdbSearch() {
    const finalName = document.getElementById('final-import-name').value.trim();
    if (finalName) {
        // Dispatch event to be caught by editAnime.js to show the TMDB search view
        document.dispatchEvent(new CustomEvent('show:tmdb-search-for-bulk', { detail: { keyword: finalName } }));
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
