import { apiFetch } from '../api.js';
import { switchView } from '../ui.js';

// State
let _currentSearchSelectionData = null;

// DOM Elements
let editAnimeView, editAnimeForm, editAnimeTypeSelect, selectEgidBtn;
let bangumiSearchView, tmdbSearchView, egidView, reassociateView;
let backToEditAnimeFromBgmSearchBtn, backToEditAnimeFromTmdbSearchBtn, backToEditFromEgidBtn, backToEditFromReassociateBtn;

function initializeElements() {
    editAnimeView = document.getElementById('edit-anime-view');
    editAnimeForm = document.getElementById('edit-anime-form');
    editAnimeTypeSelect = document.getElementById('edit-anime-type');
    selectEgidBtn = document.getElementById('select-egid-btn');

    bangumiSearchView = document.getElementById('bangumi-search-view');
    tmdbSearchView = document.getElementById('tmdb-search-view');
    egidView = document.getElementById('egid-view');
    reassociateView = document.getElementById('reassociate-view');

    backToEditAnimeFromBgmSearchBtn = document.getElementById('back-to-edit-anime-from-bgm-search-btn');
    backToEditAnimeFromTmdbSearchBtn = document.getElementById('back-to-edit-anime-from-tmdb-search-btn');
    backToEditFromEgidBtn = document.getElementById('back-to-edit-from-egid-btn');
    backToEditFromReassociateBtn = document.getElementById('back-to-edit-from-reassociate-btn');
}

async function showEditAnimeView(animeId) {
    switchView('edit-anime-view');
    clearSearchSelectionState();
    editAnimeForm.reset();
    editAnimeForm.querySelector('button[type="submit"]').disabled = true;

    try {
        const details = await apiFetch(`/api/ui/library/anime/${animeId}/details`);
        populateEditForm(details);
    } catch (error) {
        alert(`加载编辑信息失败: ${error.message}`);
        switchView('library-view');
    } finally {
        editAnimeForm.querySelector('button[type="submit"]').disabled = false;
    }
}

function populateEditForm(details) {
    document.getElementById('edit-anime-id').value = details.anime_id;
    document.getElementById('edit-anime-title').value = details.title;
    editAnimeTypeSelect.value = details.type;
    document.getElementById('edit-anime-season').value = details.season;
    document.getElementById('edit-anime-episode-count').value = details.episode_count || '';
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
    handleAnimeTypeChange();
    updateEgidSelectButtonState();
}

// ... (The rest of the functions from app.js related to editing, searching, etc.)
// ... handleEditAnimeSave, handleAnimeTypeChange, handleSearchBgmId, etc.

export function setupEditAnimeEventListeners() {
    initializeElements();
    document.addEventListener('show:edit-anime', (e) => showEditAnimeView(e.detail.animeId));
    // ... add all other event listeners for this module
}
