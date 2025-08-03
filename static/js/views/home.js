import { apiFetch } from '../api.js';
import { toggleLoader, switchView } from '../ui.js';

let logRefreshInterval = null;
let originalSearchResults = [];
let itemsForBulkImport = [];

const typeMap = {
    'tv_series': '电视节目',
    'movie': '电影/剧场版'
};

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
    document.getElementById('enable-episode-search').addEventListener('change', (e) => {
        document.getElementById('episode-search-inputs').classList.toggle('hidden', !e.target.checked);
    });
    document.getElementById('insert-episode-btn').addEventListener('click', () => {
        const season = document.getElementById('search-season').value;
        const episode = document.getElementById('search-episode').value;
        if (!season || !episode) return;
        const formatted = ` S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`;
        insertAtCursor(document.getElementById('search-keyword'), formatted);
    });
    document.querySelectorAll('input[name="bulk-import-mode"]').forEach(radio => {
        radio.addEventListener('change', handleBulkImportModeChange);
    });

    // Bulk Import View
    document.getElementById('cancel-bulk-import-btn').addEventListener('click', () => switchView('home-view'));
    document.getElementById('confirm-bulk-import-btn').addEventListener('click', handleConfirmBulkImport);
    document.getElementById('search-tmdb-for-bulk-btn').addEventListener('click', handleBulkTmdbSearch);

    // Listen to global events
    document.addEventListener('auth:status-changed', (e) => {
        if (e.detail.loggedIn) {
            startLogRefresh();
        } else {
            stopLogRefresh();
        }
    });
    document.addEventListener('tmdb-search:selected-for-bulk', (e) => {
        // Listen for the event dispatched from editAnime.js
        const chineseName = e.detail.aliases_cn && e.detail.aliases_cn.length > 0 ? e.detail.aliases_cn[0] : null;
        document.getElementById('final-import-name').value = chineseName || e.detail.name_en || e.detail.name_jp || '';
        document.getElementById('final-import-tmdb-id').value = e.detail.id || '';
        switchView('bulk-import-view'); // Switch back to the bulk import view
    });
}

function handleBulkImportModeChange(e) {
    const unifiedFields = document.getElementById('unified-import-fields');
    unifiedFields.classList.toggle('hidden', e.target.value !== 'unified');
}

function insertAtCursor(inputField, textToInsert) {
    const startPos = inputField.selectionStart;
    const endPos = inputField.selectionEnd;
    const text = inputField.value;
    inputField.value = text.substring(0, startPos) + textToInsert + text.substring(endPos, text.length);
    inputField.focus();
    inputField.selectionStart = startPos + textToInsert.length;
    inputField.selectionEnd = startPos + textToInsert.length;
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
    let keyword = document.getElementById('search-keyword').value.trim();
    if (!keyword) {
        alert('请输入搜索关键词。');
        return;
    }

    const enableEpisodeSearch = document.getElementById('enable-episode-search').checked;
    const season = document.getElementById('search-season').value;
    const episode = document.getElementById('search-episode').value;

    // 如果启用了精确搜索，并且填写了季和集，则拼接字符串
    // 同时检查原始关键词中是否已包含 SXXEXX 格式，避免重复拼接
    if (enableEpisodeSearch && season && episode && !/S\d+E\d+/i.test(keyword)) {
        keyword = `${keyword} S${String(season).padStart(2, '0')}E${String(episode).padStart(2, '0')}`;
    }

    document.getElementById('results-list').innerHTML = '';
    toggleLoader(true);

    try {
        const data = await apiFetch(`/api/ui/search/provider?keyword=${encodeURIComponent(keyword)}`);
        const processedResults = (data.results || []).map(item => ({
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
        // 新增：匹配Unicode罗马数字 (e.g., Ⅲ)
        /\s+([Ⅰ-Ⅻ])\b/i,
        /\s+([IVXLCDM]+)$/i // Roman numerals at the end of the string
    ];

    const chineseNumMap = { '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10 };
    // 新增：Unicode罗马数字到整数的映射
    const unicodeRomanMap = { 'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3, 'Ⅳ': 4, 'Ⅴ': 5, 'Ⅵ': 6, 'Ⅶ': 7, 'Ⅷ': 8, 'Ⅸ': 9, 'Ⅹ': 10, 'Ⅺ': 11, 'Ⅻ': 12 };

    for (const pattern of patterns) {
        const match = title.match(pattern);
        if (match && match[1]) {
            const numStr = match[1];
            if (numStr.match(/^\d+$/)) {
                return parseInt(numStr, 10);
            } else if (chineseNumMap[numStr]) {
                return chineseNumMap[numStr];
            } else if (unicodeRomanMap[numStr.toUpperCase()]) {
                return unicodeRomanMap[numStr.toUpperCase()];
            } else { // Fallback for ASCII Roman numerals
                try {
                    return romanToInt(numStr.toUpperCase());
                } catch {
                    // ignore if not a valid roman numeral
                }
            }
        }
    }
    return 1; // Default to season 1
}

function romanToInt(s) {
    const map = { 'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000 };
    let result = 0;
    for (let i = 0; i < s.length; i++) {
        const current = map[s[i]];
        const next = map[s[i + 1]];
        if (next && current < next) {
            result -= current;
        } else {
            result += current;
        }
    }
    return result;
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
        const displayType = typeMap[item.type] || item.type;
        
        const metaParts = [
            `源: ${item.provider}`,
            `类型: ${displayType}`,
            `年份: ${item.year || 'N/A'}`
        ];
        if (item.type === 'tv_series') {
            metaParts.push(`季度: ${String(item.season).padStart(2, '0')}`);
            metaParts.push(`总集数: ${item.episodeCount || '未知'}`);
            if (item.currentEpisodeIndex) {
                // 修正：如果搜索了特定分集，则只追加集数信息
                metaParts.push(`集: ${String(item.currentEpisodeIndex).padStart(2, '0')}`);
            }
        }
        infoDiv.innerHTML = `<p class="title">${item.title}</p><p class="meta">${metaParts.join(' | ')}</p>`;

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

    // Always show the bulk import view
    _showBulkImportView(itemsForBulkImport);
}

function _showBulkImportView(items) {
    switchView('bulk-import-view');
    const listEl = document.getElementById('bulk-import-list');
    listEl.innerHTML = '';
    items.forEach(item => {
        const li = document.createElement('li');
        const displayType = typeMap[item.type] || item.type;
        li.textContent = `${item.title} (源: ${item.provider}, 类型: ${displayType}, 季: ${item.season})`;
        li.style.cursor = 'pointer';
        li.addEventListener('click', () => {
            document.getElementById('final-import-name').value = item.title;
        });
        listEl.appendChild(li);
    });

    const uniqueTitles = new Set(items.map(item => item.title));
    const unifiedModeRadio = document.querySelector('input[name="bulk-import-mode"][value="unified"]');
    const separateModeRadio = document.querySelector('input[name="bulk-import-mode"][value="separate"]');
    const unifiedFields = document.getElementById('unified-import-fields');
    const infoParagraph = document.querySelector('#bulk-import-view .form-card p');

    if (uniqueTitles.size === 1) {
        infoParagraph.textContent = `您选择了 ${items.length} 个标题相同的条目。请确认导入模式。`;
        unifiedModeRadio.checked = true;
        unifiedFields.classList.remove('hidden');
        document.getElementById('final-import-name').value = items[0].title;
    } else {
        infoParagraph.textContent = `检测到您选择的媒体标题不一致。请指定导入模式。`;
        separateModeRadio.checked = true;
        unifiedFields.classList.add('hidden');
        document.getElementById('final-import-name').value = items[0].title; // Still set a default
    }

    document.getElementById('final-import-tmdb-id').value = '';
}

async function _performSeparateBulkImport(items) {
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
                        current_episode_index: item.currentEpisodeIndex, tmdb_id: null
                    }),
                });
                console.log(`提交独立导入任务 ${item.title} (源: ${item.provider}) 成功: ${data.message}`);
            } catch (error) {
                if (error.message && error.message.includes("该数据源已存在于弹幕库中")) {
                     console.warn(`跳过已存在的源: ${item.title} (源: ${item.provider})`);
                } else {
                    console.error(`提交独立导入任务 ${item.title} (源: ${item.provider}) 失败: ${error.message || error}`);
                }
            }
            await new Promise(resolve => setTimeout(resolve, 200));
        }
        alert("批量导入任务已提交，请在任务管理器中查看进度。");
    } finally {
        bulkImportBtn.disabled = false;
        bulkImportBtn.textContent = '批量导入';
        switchView('home-view');
    }
}

async function _performUnifiedBulkImport(items, finalTitle, finalTmdbId = null) {
    const bulkImportBtn = document.getElementById('bulk-import-btn');
    bulkImportBtn.disabled = true;
    bulkImportBtn.textContent = '批量导入中...';

    try {
        for (const item of items) {
            try {
                const data = await apiFetch('/api/ui/import', {
                    method: 'POST',
                    body: JSON.stringify({
                        provider: item.provider, media_id: item.mediaId, anime_title: finalTitle,
                        type: item.type, season: item.season, image_url: item.imageUrl, douban_id: item.douban_id,
                        current_episode_index: item.currentEpisodeIndex,
                        tmdb_id: finalTmdbId // Pass the final TMDB ID
                    }),
                });
                console.log(`提交导入任务 ${finalTitle} (源: ${item.provider}) 成功: ${data.message}`);
            } catch (error) {
                if (error.message && error.message.includes("该数据源已存在于弹幕库中")) {
                    console.warn(`跳过已存在的源: ${finalTitle} (源: ${item.provider})`);
                } else {
                    console.error(`提交导入任务 ${finalTitle} (源: ${item.provider}) 失败: ${error.message || error}`);
                }
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
    const importMode = document.querySelector('input[name="bulk-import-mode"]:checked').value;

    if (importMode === 'unified') {
        const finalTitle = document.getElementById('final-import-name').value.trim();
        const finalTmdbId = document.getElementById('final-import-tmdb-id').value.trim() || null;
        if (!finalTitle) {
            alert("最终导入名称不能为空。");
            return;
        }
        if (itemsForBulkImport.length > 0) {
            _performUnifiedBulkImport(itemsForBulkImport, finalTitle, finalTmdbId);
        }
    } else { // 'separate' mode
        if (itemsForBulkImport.length > 0 && confirm(`确定要将 ${itemsForBulkImport.length} 个条目作为独立作品分别导入吗？`)) {
            _performSeparateBulkImport(itemsForBulkImport);
        }
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
