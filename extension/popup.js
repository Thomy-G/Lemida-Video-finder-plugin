// popup.js - Lemida Video Finder UI Controller
(function () {
  'use strict';

  // State
  let currentVideos = [];
  let currentCourse = { title: 'Unknown Course', id: '-', url: '' };
  let currentTabId = null;
  let lastDiagnostics = null;
  const DEFAULT_XPATH = '/html/body/div[3]/div[5]/div/div/div[2]/div[2]/div/section/div[2]/div[1]/div[1]/div/video/source';

  // DOM Elements
  const videoListEl = document.getElementById('video-list');
  const countBadgeEl = document.getElementById('video-count-badge');
  const courseTitleEl = document.getElementById('course-title');
  const courseIdTagEl = document.getElementById('course-id-tag');
  const notLemidaBanner = document.getElementById('not-lemida-banner');
  const searchInput = document.getElementById('search-input');
  const clearSearchBtn = document.getElementById('clear-search');
  const refreshBtn = document.getElementById('refresh-btn');
  const copyAllBtn = document.getElementById('copy-all-btn');
  const deepScanBtn = document.getElementById('deep-scan-btn');
  const exportDropdownBtn = document.getElementById('export-dropdown-btn');
  const exportMenu = document.getElementById('export-menu');
  const exportTxtBtn = document.getElementById('export-txt-btn');
  const exportJsonBtn = document.getElementById('export-json-btn');
  const exportM3uBtn = document.getElementById('export-m3u-btn');
  const exportYtdlpBtn = document.getElementById('export-ytdlp-btn');
  const exportCliBtn = document.getElementById('export-cli-btn');
  const toggleXpathBtn = document.getElementById('toggle-xpath-btn');
  const xpathDrawer = document.getElementById('xpath-drawer');
  const closeDrawerBtn = document.getElementById('close-drawer-btn');
  const customXpathInput = document.getElementById('custom-xpath-input');
  const applyXpathBtn = document.getElementById('apply-xpath-btn');
  const resetXpathBtn = document.getElementById('reset-xpath-btn');
  const copySessionBtn = document.getElementById('copy-session-btn');
  const diagnoseBtn = document.getElementById('diagnose-btn');
  const diagDrawer = document.getElementById('diag-drawer');
  const closeDiagBtn = document.getElementById('close-diag-btn');
  const diagContent = document.getElementById('diag-content');
  const copyDiagBtn = document.getElementById('copy-diag-btn');
  const toastEl = document.getElementById('toast');

  /**
   * Filter out any internal Moodle page URLs so only backend video hosters are used
   */
  function filterBackendHosters(videos) {
    if (!videos || !Array.isArray(videos)) return [];
    return videos.filter(v => v.url && !v.url.includes('/mod/') && !v.url.includes('/course/') && !v.url.includes('view.php'));
  }

  function showToast(message) {
    toastEl.textContent = message;
    toastEl.classList.remove('hidden');
    toastEl.style.animation = 'none';
    toastEl.offsetHeight;
    toastEl.style.animation = null;

    setTimeout(() => {
      toastEl.classList.add('hidden');
    }, 2200);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function renderVideos(videosToRender, activityCount = 0) {
    const validVideos = filterBackendHosters(videosToRender);

    if (validVideos.length === 0) {
      if (activityCount > 0) {
        videoListEl.innerHTML = `
          <div class="empty-state" style="padding: 24px 16px;">
            <div style="font-size: 24px;">⚡</div>
            <h4 style="color: #f8fafc; font-size: 13px;">Found ${activityCount} Video Lectures</h4>
            <p style="font-size: 11.5px; color: #94a3b8; line-height: 1.5;">
              Extracting direct backend video hosters (.mp4 stream URLs)...
            </p>
            <button id="empty-deep-scan-btn" class="btn btn-primary" style="margin-top: 8px;">
              ⚡ Extract Backend Video Hosters
            </button>
          </div>
        `;
        const emptyDeep = document.getElementById('empty-deep-scan-btn');
        if (emptyDeep) emptyDeep.addEventListener('click', runDeepScan);
        return;
      }

      videoListEl.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 24 24" width="32" height="32" stroke="currentColor" stroke-width="1.5" fill="none" style="color: #64748b;">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          <p>No backend video hosters detected on this page.</p>
          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <button id="empty-deep-scan-btn" class="btn btn-sm btn-secondary">Extract Video Streams</button>
            <button id="empty-diag-btn" class="btn btn-sm btn-ghost">🔍 Diagnose Page</button>
          </div>
        </div>
      `;
      const emptyDeep = document.getElementById('empty-deep-scan-btn');
      if (emptyDeep) emptyDeep.addEventListener('click', runDeepScan);
      const emptyDiag = document.getElementById('empty-diag-btn');
      if (emptyDiag) emptyDiag.addEventListener('click', runDiagnosticsAction);
      return;
    }

    let html = '';
    validVideos.forEach((vid, index) => {
      // Determine host label (e.g. Oracle Cloud, Kaltura, Panopto, MP4)
      let hostLabel = 'MP4';
      if (vid.url.includes('oraclecloud.com')) hostLabel = 'Oracle Cloud';
      else if (vid.url.includes('kaltura')) hostLabel = 'Kaltura';
      else if (vid.url.includes('panopto')) hostLabel = 'Panopto';

      html += `
        <div class="video-card" data-id="${vid.id}">
          <div class="video-card-header">
            <div class="video-title-area">
              <span class="video-index">${index + 1}</span>
              <span class="video-title" title="${escapeHtml(vid.title)}">${escapeHtml(vid.title)}</span>
            </div>
            <div class="video-meta-tags">
              <span class="meta-pill meta-pill-section" title="Section: ${escapeHtml(vid.section)}">${escapeHtml(vid.section)}</span>
              <span class="meta-pill meta-pill-type">${escapeHtml(hostLabel)}</span>
            </div>
          </div>

          <div class="video-url-container">
            <span class="video-url-text" title="${escapeHtml(vid.url)}">${escapeHtml(vid.url)}</span>
          </div>

          <div class="card-actions">
            <button class="action-chip action-chip-primary copy-single-btn" data-url="${escapeHtml(vid.url)}">
              📋 Copy Direct URL
            </button>
            <button class="action-chip open-tab-btn" data-url="${escapeHtml(vid.url)}">
              ▶ Play Stream
            </button>
            <button class="action-chip copy-ytdlp-single-btn" data-url="${escapeHtml(vid.url)}" data-title="${escapeHtml(vid.title)}">
              💻 yt-dlp
            </button>
          </div>
        </div>
      `;
    });

    videoListEl.innerHTML = html;

    // Attach listeners
    videoListEl.querySelectorAll('.copy-single-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const url = btn.getAttribute('data-url');
        navigator.clipboard.writeText(url).then(() => showToast('Direct video URL copied!'));
      });
    });

    videoListEl.querySelectorAll('.open-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const url = btn.getAttribute('data-url');
        chrome.tabs.create({ url });
      });
    });

    videoListEl.querySelectorAll('.copy-ytdlp-single-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const url = btn.getAttribute('data-url');
        const title = btn.getAttribute('data-title').replace(/["\\]/g, '');
        const cmd = `yt-dlp "${url}" -o "${title}.%(ext)s"`;
        navigator.clipboard.writeText(cmd).then(() => showToast('yt-dlp command copied!'));
      });
    });
  }

  function filterVideos() {
    const q = searchInput.value.trim().toLowerCase();
    const valid = filterBackendHosters(currentVideos);
    if (!q) {
      clearSearchBtn.classList.add('hidden');
      renderVideos(valid);
      return;
    }

    clearSearchBtn.classList.remove('hidden');
    const filtered = valid.filter(v =>
      (v.title && v.title.toLowerCase().includes(q)) ||
      (v.section && v.section.toLowerCase().includes(q)) ||
      (v.url && v.url.toLowerCase().includes(q))
    );
    renderVideos(filtered);
  }

  function performScan(customXPath = null, retryCount = 0) {
    if (!currentTabId) return;

    videoListEl.innerHTML = `
      <div class="empty-state">
        <div class="spinner"></div>
        <p>Scanning course page for videos...</p>
      </div>
    `;

    chrome.tabs.sendMessage(
      currentTabId,
      { action: 'SCAN_VIDEOS', customXPath },
      (response) => {
        if (chrome.runtime.lastError || !response) {
          if (retryCount === 0) {
            chrome.scripting.executeScript({
              target: { tabId: currentTabId, allFrames: true },
              files: ['content.js']
            }, () => {
              setTimeout(() => performScan(customXPath, 1), 150);
            });
            return;
          }

          courseTitleEl.textContent = 'Connection Error';
          videoListEl.innerHTML = `
            <div class="empty-state">
              <p>Please refresh the Lemida tab (F5) and open the extension again.</p>
              <button id="retry-scan-btn" class="btn btn-sm btn-primary">Refresh & Retry</button>
            </div>
          `;
          const retryBtn = document.getElementById('retry-scan-btn');
          if (retryBtn) {
            retryBtn.addEventListener('click', () => {
              chrome.tabs.reload(currentTabId, () => window.close());
            });
          }
          return;
        }

        // Filter out any moodle page URLs immediately
        currentVideos = filterBackendHosters(response.videos || []);
        currentCourse = response.course || currentCourse;

        courseTitleEl.textContent = currentCourse.title || 'Lemida Course';
        courseTitleEl.title = currentCourse.title || '';
        courseIdTagEl.textContent = `ID: ${currentCourse.id || '-'}`;
        countBadgeEl.textContent = `${currentVideos.length} Video${currentVideos.length === 1 ? '' : 's'}`;

        // If 0 direct videos on overview page, but lecture activities exist:
        // Automatically start extracting the backend video hosters!
        if (currentVideos.length === 0 && (response.activityLinksCount || 0) > 0) {
          runDeepScan();
        } else {
          renderVideos(currentVideos, response.activityLinksCount || 0);
        }
      }
    );
  }

  function runDeepScan() {
    if (!currentTabId) return;

    deepScanBtn.disabled = true;
    deepScanBtn.innerHTML = `
      <div class="spinner" style="width: 12px; height: 12px; border-width: 2px;"></div>
      Extracting Streams...
    `;

    videoListEl.innerHTML = `
      <div class="empty-state">
        <div class="spinner"></div>
        <p>Extracting direct backend video hosters...</p>
        <span style="font-size: 11px; color: #64748b;">Visiting lecture pages to extract direct .mp4 streams</span>
      </div>
    `;

    chrome.tabs.sendMessage(currentTabId, { action: 'DEEP_SCAN' }, (response) => {
      deepScanBtn.disabled = false;
      deepScanBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        Deep Scan
      `;

      if (response && response.videos) {
        // STRICT FILTER: ONLY backend video hosters (never Moodle page links)
        currentVideos = filterBackendHosters(response.videos);
        countBadgeEl.textContent = `${currentVideos.length} Video${currentVideos.length === 1 ? '' : 's'}`;
        renderVideos(currentVideos, 0);
        showToast(`Extracted ${currentVideos.length} direct video URLs!`);
      } else {
        showToast('Extraction completed.');
      }
    });
  }

  function runDiagnosticsAction() {
    if (!currentTabId) return;
    diagDrawer.classList.remove('hidden');
    xpathDrawer.classList.add('hidden');
    diagContent.textContent = 'Analyzing DOM elements on page...';

    chrome.tabs.sendMessage(currentTabId, { action: 'DIAGNOSE' }, (res) => {
      if (chrome.runtime.lastError || !res || !res.diagnostics) {
        diagContent.textContent = 'Could not run diagnostics. Try refreshing the Lemida page.';
        return;
      }
      lastDiagnostics = res.diagnostics;
      diagContent.textContent = JSON.stringify(res.diagnostics, null, 2);
    });
  }

  function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(`Downloaded ${filename}`);
  }

  function initApp() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs[0]) return;
      const tab = tabs[0];
      currentTabId = tab.id;
      const url = tab.url || '';

      if (!url.includes('lemida.biu.ac.il')) {
        notLemidaBanner.classList.remove('hidden');
        courseTitleEl.textContent = 'Not on Lemida';
        countBadgeEl.textContent = 'Inactive';
        videoListEl.innerHTML = `
          <div class="empty-state">
            <p>Open a course page on <strong>lemida.biu.ac.il</strong> to start finding videos.</p>
          </div>
        `;
        return;
      }

      notLemidaBanner.classList.add('hidden');
      performScan();
    });
  }

  // Event Listeners
  refreshBtn.addEventListener('click', () => performScan(customXpathInput.value.trim()));
  searchInput.addEventListener('input', filterVideos);
  clearSearchBtn.addEventListener('click', () => {
    searchInput.value = '';
    filterVideos();
  });

  // Copy All Links - ONLY backend video hosters
  copyAllBtn.addEventListener('click', () => {
    const valid = filterBackendHosters(currentVideos);
    if (!valid.length) return showToast('No direct video links found.');
    const allLinks = valid.map(v => v.url).join('\n');
    navigator.clipboard.writeText(allLinks).then(() => {
      showToast(`Copied ${valid.length} direct video URLs!`);
    });
  });

  deepScanBtn.addEventListener('click', runDeepScan);

  exportDropdownBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    exportMenu.classList.toggle('hidden');
  });

  document.addEventListener('click', () => {
    exportMenu.classList.add('hidden');
  });

  exportTxtBtn.addEventListener('click', () => {
    const valid = filterBackendHosters(currentVideos);
    if (!valid.length) return showToast('No direct video links to export');
    const lines = valid.map(v => `${v.title} [${v.section}]\n${v.url}\n`);
    const content = `Course: ${currentCourse.title} (ID: ${currentCourse.id})\nTotal Videos: ${valid.length}\n\n` + lines.join('\n');
    downloadFile(content, `lemida_course_${currentCourse.id}_videos.txt`, 'text/plain;charset=utf-8');
  });

  exportJsonBtn.addEventListener('click', () => {
    const valid = filterBackendHosters(currentVideos);
    if (!valid.length) return showToast('No direct video links to export');
    const data = {
      course: currentCourse,
      total: valid.length,
      extractedAt: new Date().toISOString(),
      videos: valid
    };
    downloadFile(JSON.stringify(data, null, 2), `lemida_course_${currentCourse.id}_videos.json`, 'application/json');
  });

  exportM3uBtn.addEventListener('click', () => {
    const valid = filterBackendHosters(currentVideos);
    if (!valid.length) return showToast('No direct video links to export');
    let m3u = '#EXTM3U\n';
    valid.forEach(v => {
      m3u += `#EXTINF:-1 group-title="${v.section}",${v.title}\n${v.url}\n`;
    });
    downloadFile(m3u, `lemida_course_${currentCourse.id}.m3u`, 'audio/x-mpegurl');
  });

  exportYtdlpBtn.addEventListener('click', () => {
    const valid = filterBackendHosters(currentVideos);
    if (!valid.length) return showToast('No direct video links to export');
    const commands = valid.map(v => {
      const cleanTitle = v.title.replace(/["\\]/g, '');
      return `yt-dlp "${v.url}" -o "${cleanTitle}.%(ext)s"`;
    }).join('\n');
    navigator.clipboard.writeText(commands).then(() => {
      showToast('Copied yt-dlp commands for all direct streams!');
    });
  });

  exportCliBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'GET_COOKIES' }, (res) => {
      const session = res && res.moodleSession ? res.moodleSession : '';
      const courseId = currentCourse.id !== '-' ? currentCourse.id : '108883';
      const cmd = session
        ? `uv run lemida-cli fetch ${courseId} --cookie "${session}" --links-only`
        : `uv run lemida-cli fetch ${courseId} --links-only`;

      navigator.clipboard.writeText(cmd).then(() => {
        showToast('Copied CLI command to clipboard!');
      });
    });
  });

  toggleXpathBtn.addEventListener('click', () => {
    xpathDrawer.classList.toggle('hidden');
    diagDrawer.classList.add('hidden');
  });

  closeDrawerBtn.addEventListener('click', () => xpathDrawer.classList.add('hidden'));
  diagnoseBtn.addEventListener('click', runDiagnosticsAction);
  closeDiagBtn.addEventListener('click', () => diagDrawer.classList.add('hidden'));

  copyDiagBtn.addEventListener('click', () => {
    if (diagContent.textContent) {
      navigator.clipboard.writeText(diagContent.textContent).then(() => {
        showToast('Copied diagnostics to clipboard!');
      });
    }
  });

  applyXpathBtn.addEventListener('click', () => {
    const custom = customXpathInput.value.trim();
    xpathDrawer.classList.add('hidden');
    performScan(custom);
    showToast('Applied custom XPath!');
  });

  resetXpathBtn.addEventListener('click', () => {
    customXpathInput.value = DEFAULT_XPATH;
    performScan();
    showToast('Reset to default XPath.');
  });

  copySessionBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'GET_COOKIES' }, (res) => {
      if (res && res.cookieHeader) {
        navigator.clipboard.writeText(res.cookieHeader).then(() => {
          showToast('Copied Lemida cookie string!');
        });
      } else {
        showToast('Could not read cookies.');
      }
    });
  });

  initApp();
})();
