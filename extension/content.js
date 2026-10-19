// content.js - Lemida Video Finder Content Script
(function () {
  'use strict';

  // Primary user-provided XPath:
  const PRIMARY_XPATH = '/html/body/div[3]/div[5]/div/div/div[2]/div[2]/div/section/div[2]/div[1]/div[1]/div/video/source';

  /**
   * Safe sendMessage wrapper that ignores disconnected extension errors
   */
  function safeSendMessage(msg, callback) {
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id) {
      try {
        chrome.runtime.sendMessage(msg, res => {
          if (chrome.runtime.lastError) {
            // Context invalidated or ignored
            return;
          }
          if (callback) callback(res);
        });
      } catch (e) {}
    }
  }

  /**
   * Evaluates an XPath expression with namespace tolerance
   */
  function evaluateXPath(xpath, contextNode = document) {
    const results = [];
    try {
      const query = contextNode.evaluate(
        xpath,
        contextNode,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      for (let i = 0; i < query.snapshotLength; i++) {
        const node = query.snapshotItem(i);
        if (node) results.push(node);
      }
    } catch (e) {}

    // Fallback if 0 results
    if (results.length === 0 && !xpath.startsWith('/')) {
      try {
        const agnosticXPath = xpath.replace(/\b([a-zA-Z]+)\b/g, (match) => {
          if (['div', 'section', 'video', 'source', 'iframe', 'a', 'span', 'h1', 'h2', 'h3', 'h4'].includes(match.toLowerCase())) {
            return `*[local-name()='${match}']`;
          }
          return match;
        });
        const query2 = contextNode.evaluate(
          agnosticXPath,
          contextNode,
          null,
          XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
          null
        );
        for (let i = 0; i < query2.snapshotLength; i++) {
          const node = query2.snapshotItem(i);
          if (node) results.push(node);
        }
      } catch (err) {}
    }

    return results;
  }

  /**
   * Attempts to determine a clean, user-friendly title for the video element
   */
  function extractVideoTitle(element) {
    if (!element) return 'Lemida Video';
    if (element.getAttribute && element.getAttribute('title')) return element.getAttribute('title').trim();
    if (element.getAttribute && element.getAttribute('aria-label')) return element.getAttribute('aria-label').trim();

    const videoEl = element.tagName && element.tagName.toLowerCase() === 'video' ? element : (element.closest ? element.closest('video') : null);
    if (videoEl) {
      if (videoEl.getAttribute('title')) return videoEl.getAttribute('title').trim();
      if (videoEl.getAttribute('aria-label')) return videoEl.getAttribute('aria-label').trim();
    }

    // Check page header first (especially on mod/videostream subpages!)
    const pageHeading = document.querySelector('.page-header-headings h1, #page-header h1, h1, .page-header-title');
    if (pageHeading && pageHeading.textContent.trim()) {
      const hText = pageHeading.textContent.trim();
      if (!hText.toLowerCase().includes('שיטות סטטיסטיות') && !hText.toLowerCase().includes('קורס')) {
        return hText;
      }
    }

    // Nearest activity container title
    if (element.closest) {
      const activityContainer = element.closest('.activity-item, .activityinstance, .activity, .contentnode, .mod-indent-outer, li.activity');
      if (activityContainer) {
        const nameEl = activityContainer.querySelector('.instancename, .activityname, .activity-title, h3, h4, h5');
        if (nameEl) {
          const clone = nameEl.cloneNode(true);
          const accesshide = clone.querySelectorAll('.accesshide, .sr-only, .badge');
          accesshide.forEach(el => el.remove());
          const text = clone.textContent.trim();
          if (text) return text;
        }
      }

      // Preceding heading
      let prev = (videoEl || element).previousElementSibling;
      while (prev) {
        if (/^H[1-6]$/i.test(prev.tagName) || prev.classList.contains('title')) {
          const text = prev.textContent.trim();
          if (text) return text;
        }
        prev = prev.previousElementSibling;
      }

      // Section title fallback
      const section = element.closest('section, .section, li.section');
      if (section) {
        const secHeader = section.querySelector('.sectionname, .section-title, h3.section-title, h3, h4');
        if (secHeader && secHeader.textContent.trim()) {
          return `${secHeader.textContent.trim()} (Video)`;
        }
      }
    }

    // Fallback from filename in URL
    const src = element.src || (element.getAttribute ? element.getAttribute('src') : '') || '';
    if (src) {
      try {
        const urlObj = new URL(src, window.location.href);
        const filename = urlObj.pathname.split('/').pop();
        if (filename && filename.length > 3) {
          return decodeURIComponent(filename);
        }
      } catch (err) {}
    }

    return document.title || 'Lemida Video';
  }

  /**
   * Finds the section name / topic for a given element
   */
  function extractSectionName(element) {
    if (!element || !element.closest) return 'General';
    const section = element.closest('section, .section, li.section');
    if (section) {
      const secHeader = section.querySelector('.sectionname, .section-title, h3.section-title, h3, h4');
      if (secHeader) {
        return secHeader.textContent.trim();
      }
      const sectionId = section.getAttribute('id') || section.getAttribute('data-sectionid') || '';
      if (sectionId) return `Section ${sectionId.replace(/\D+/g, '')}`;
    }
    return 'General';
  }

  /**
   * Scans for linked Moodle video activities (specifically mod/videostream)
   */
  function findVideoActivityLinks() {
    const activityLinks = [];
    const seen = new Set();

    // Prioritize videostream links
    const selectors = [
      'a[href*="/mod/videostream/view.php"]',
      'a[href*="/mod/videostream/"]',
      'a[href*="/mod/kalvidres/view.php"]',
      'a[href*="/mod/panopto/view.php"]',
      'a[href*="/mod/resource/view.php"]',
      'a[href*="/mod/page/view.php"]'
    ];

    const links = document.querySelectorAll(selectors.join(','));
    for (const a of links) {
      const href = a.href || a.getAttribute('href');
      if (!href || seen.has(href)) continue;

      const parent = a.closest ? a.closest('.activity-item, .activityinstance, li.activity, .activity') : null;
      const text = (a.textContent + ' ' + (parent ? parent.textContent : '')).toLowerCase();
      
      const isExplicitVideoMod = href.includes('videostream') || href.includes('kalvidres') || href.includes('panopto');
      const hasVideoClues =
        text.includes('video') ||
        text.includes('recording') ||
        text.includes('lecture') ||
        text.includes('הקלטה') ||
        text.includes('הרצאה') ||
        text.includes('שיעור') ||
        text.includes('וידאו');

      if (isExplicitVideoMod || hasVideoClues) {
        seen.add(href);
        const nameNode = a.querySelector('.instancename') || a;
        let title = nameNode.textContent.trim();
        // Remove trailing badge words if any
        title = title.replace(/\s*(וידאו|הקלטה|VideoStream|Video)\s*$/i, '').trim() || title;
        const section = extractSectionName(a);
        activityLinks.push({ url: href, title, section, isVideoStream: href.includes('videostream') });
      }
    }

    return activityLinks;
  }

  /**
   * Comprehensive scanner on the active page
   */
  function scanPageVideos(customXPath = null) {
    const found = [];
    const seenUrls = new Set();

    function addVideo(el, rawUrl, type = 'video/mp4', matchedSelector = 'dom_query', sourceType = 'html5_video', customTitle = null) {
      if (!rawUrl) return;
      try {
        const absUrl = new URL(rawUrl, window.location.href).href;
        if (seenUrls.has(absUrl)) return;
        if (absUrl.startsWith('javascript:')) return;
        if (absUrl.includes('/mod/') || absUrl.includes('/course/') || absUrl.includes('view.php')) return;

        seenUrls.add(absUrl);
        const title = customTitle || extractVideoTitle(el);
        const section = extractSectionName(el);

        found.push({
          id: `vid_${found.length + 1}`,
          title,
          section,
          url: absUrl,
          type,
          xpathMatched: matchedSelector,
          sourceType,
          isDirectStream: true
        });
      } catch (e) {}
    }

    // 1. Try Custom XPath or User's exact XPath
    const targetXPath = customXPath || PRIMARY_XPATH;
    const exactMatches = evaluateXPath(targetXPath, document);
    for (const el of exactMatches) {
      const src = el.src || (el.getAttribute ? el.getAttribute('src') : null) || (el.getAttribute ? el.getAttribute('data-src') : null);
      if (src) {
        addVideo(el, src, el.getAttribute ? (el.getAttribute('type') || 'video/mp4') : 'video/mp4', targetXPath, 'xpath_match');
      }
    }

    // 2. Direct CSS Query for HTML5 <source> and <video> tags
    const videoSourceNodes = document.querySelectorAll('video source[src], video[src], source[src]');
    for (const el of videoSourceNodes) {
      const src = el.src || el.getAttribute('src') || el.getAttribute('data-src');
      if (src) {
        addVideo(el, src, el.getAttribute('type') || 'video/mp4', 'css: video source', 'html5_video');
      }
    }

    // Check video tags currentSrc
    const videoNodes = document.querySelectorAll('video');
    for (const v of videoNodes) {
      const src = v.currentSrc || v.src || v.getAttribute('src') || v.getAttribute('data-src');
      if (src) {
        addVideo(v, src, 'video/mp4', 'css: video', 'html5_video');
      }
    }

    // 3. Player elements
    const playerElements = document.querySelectorAll('[data-setup], [data-video-url], .vjs-tech, [data-player]');
    for (const p of playerElements) {
      const src = p.getAttribute('data-video-url') || p.getAttribute('src') || p.src;
      if (src) {
        addVideo(p, src, 'video/mp4', 'css: player attribute', 'player');
      }
    }

    // 4. Video Iframes (Kaltura, Panopto, MediaSpace, Embedded Players)
    const iframes = document.querySelectorAll('iframe');
    for (const iframe of iframes) {
      const src = iframe.src || iframe.getAttribute('src') || iframe.getAttribute('data-src');
      if (!src) continue;

      const lowerSrc = src.toLowerCase();
      if (
        lowerSrc.includes('kaltura') ||
        lowerSrc.includes('panopto') ||
        lowerSrc.includes('mediaspace') ||
        lowerSrc.includes('player') ||
        lowerSrc.includes('embed') ||
        lowerSrc.includes('video') ||
        lowerSrc.includes('videostream')
      ) {
        addVideo(iframe, src, 'embedded/iframe', 'iframe_embed', 'iframe');
      }
    }

    // Direct video sources on the page
    return found;
  }

  /**
   * Extracts direct video stream from a single subpage HTML
   */
  function extractStreamFromHtml(htmlText, pageUrl, customXPath = null) {
    const targetXPath = customXPath || PRIMARY_XPATH;
    let directUrl = null;
    let videoType = 'video/mp4';

    // 1. Try DOMParser with XPath & CSS
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlText, 'text/html');

      // Try exact XPath
      try {
        const xpQuery = doc.evaluate(targetXPath, doc, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        if (xpQuery.snapshotLength > 0) {
          const el = xpQuery.snapshotItem(0);
          const src = el.getAttribute('src') || el.src;
          if (src) {
            directUrl = new URL(src, pageUrl).href;
            videoType = el.getAttribute('type') || 'video/mp4';
          }
        }
      } catch (e) {}

      // Try CSS selectors on parsed doc
      if (!directUrl) {
        const sources = doc.querySelectorAll('video source[src], video[src], source[src]');
        for (const s of sources) {
          const src = s.getAttribute('src') || s.src;
          if (src) {
            directUrl = new URL(src, pageUrl).href;
            videoType = s.getAttribute('type') || 'video/mp4';
            break;
          }
        }
      }

      // Try iframe embeds
      if (!directUrl) {
        const iframes = doc.querySelectorAll('iframe[src]');
        for (const ifr of iframes) {
          const src = ifr.getAttribute('src');
          if (src && (src.includes('kaltura') || src.includes('panopto') || src.includes('video') || src.includes('embed'))) {
            directUrl = new URL(src, pageUrl).href;
            videoType = 'embedded/iframe';
            break;
          }
        }
      }
    } catch (err) {}

    // 2. High-speed Regex Fallback directly on HTML string
    if (!directUrl) {
      const sourceMatch = htmlText.match(/<source[^>]+src=["']([^"']+)["']/i);
      if (sourceMatch && sourceMatch[1]) {
        try {
          directUrl = new URL(sourceMatch[1], pageUrl).href;
        } catch (e) {}
      }

      if (!directUrl) {
        const videoMatch = htmlText.match(/<video[^>]+src=["']([^"']+)["']/i);
        if (videoMatch && videoMatch[1]) {
          try {
            directUrl = new URL(videoMatch[1], pageUrl).href;
          } catch (e) {}
        }
      }

      if (!directUrl) {
        const oracleMatch = htmlText.match(/["'](https?:\/\/[^"'\s<>]*oraclecloud\.com\/[^"'\s<>]+)["']/i);
        if (oracleMatch && oracleMatch[1]) {
          directUrl = oracleMatch[1];
        }
      }

      if (!directUrl) {
        const mp4Match = htmlText.match(/["'](https?:\/\/[^"'\s<>]+\.(?:mp4|m3u8)[^"'\s<>]*)["']/i);
        if (mp4Match && mp4Match[1]) {
          directUrl = mp4Match[1];
        }
      }
    }

    return directUrl ? { url: directUrl, type: videoType } : null;
  }

  /**
   * Deep scan: Fetches all lecture subpages concurrently and extracts direct video streams
   */
  async function performDeepScan(customXPath = null, progressCb = null) {
    const activityLinks = findVideoActivityLinks();
    const results = [];
    const seenUrls = new Set();

    let completed = 0;
    const total = activityLinks.length;

    // Concurrently fetch with batch size of 4
    const BATCH_SIZE = 4;
    for (let i = 0; i < activityLinks.length; i += BATCH_SIZE) {
      const batch = activityLinks.slice(i, i + BATCH_SIZE);
      const batchPromises = batch.map(async (act) => {
        try {
          // Abort signal with 12s timeout
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 12000);

          const response = await fetch(act.url, {
            credentials: 'include',
            signal: controller.signal
          });
          clearTimeout(timeoutId);

          if (!response.ok) return null;
          const htmlText = await response.text();

          const stream = extractStreamFromHtml(htmlText, act.url, customXPath);
          if (stream && !seenUrls.has(stream.url)) {
            // Guarantee this is a backend video hoster and NOT a Moodle page
            if (!stream.url.includes('/mod/')) {
              seenUrls.add(stream.url);
              return {
                id: `vid_${results.length + 1}`,
                title: act.title,
                section: act.section,
                url: stream.url,
                type: stream.type,
                xpathMatched: PRIMARY_XPATH,
                sourceType: 'videostream_direct',
                isDirectStream: true,
                originUrl: act.url
              };
            }
          }
          return null;
        } catch (err) {
          return null;
        } finally {
          completed++;
          if (progressCb) progressCb(completed, total);
        }
      });

      const batchResults = await Promise.all(batchPromises);
      for (const item of batchResults) {
        if (item) results.push(item);
      }
    }

    return results;
  }

  function runDiagnostics() {
    const exactMatches = evaluateXPath(PRIMARY_XPATH, document);
    const videoTags = document.querySelectorAll('video');
    const sourceTags = document.querySelectorAll('source');
    const iframes = document.querySelectorAll('iframe');
    const sections = document.querySelectorAll('section, .section, li.section');
    const activityLinks = findVideoActivityLinks();
    const videostreamLinks = document.querySelectorAll('a[href*="videostream"]');

    return {
      currentUrl: window.location.href,
      pageTitle: document.title,
      isCoursePage: window.location.href.includes('/course/view.php'),
      isVideoStreamPage: window.location.href.includes('/mod/videostream/'),
      exactXPath: PRIMARY_XPATH,
      exactXPathMatchesOnActivePage: exactMatches.length,
      videoTagsCount: videoTags.length,
      sourceTagsCount: sourceTags.length,
      iframesCount: iframes.length,
      sectionsCount: sections.length,
      videostreamLinksCount: videostreamLinks.length,
      totalActivityLinksCount: activityLinks.length,
      activitySamples: activityLinks.slice(0, 10).map(a => ({
        title: a.title,
        url: a.url,
        section: a.section
      }))
    };
  }

  function getCourseInfo() {
    const heading = document.querySelector('.page-header-headings h1, .page-header-headings, #page-header h1, h1, .page-header-title');
    const courseTitle = heading ? heading.textContent.trim() : document.title;
    const urlParams = new URLSearchParams(window.location.search);
    const courseId = urlParams.get('id') || 'Unknown';

    return {
      title: courseTitle,
      id: courseId,
      url: window.location.href
    };
  }

  // Initial badge update
  try {
    const initialVideos = scanPageVideos();
    safeSendMessage({
      action: 'UPDATE_BADGE',
      count: initialVideos.length
    });
  } catch (e) {}

  // Message listener
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'SCAN_VIDEOS') {
      const videos = scanPageVideos(request.customXPath);
      const course = getCourseInfo();
      const activityLinks = findVideoActivityLinks();

      safeSendMessage({
        action: 'UPDATE_BADGE',
        count: videos.length
      });

      sendResponse({
        success: true,
        course,
        videos,
        activityLinksCount: activityLinks.length
      });
      return true;
    }

    if (request.action === 'DEEP_SCAN') {
      performDeepScan(request.customXPath).then(videos => {
        const course = getCourseInfo();
        safeSendMessage({
          action: 'UPDATE_BADGE',
          count: videos.length
        });

        sendResponse({
          success: true,
          course,
          videos
        });
      });
      return true;
    }

    if (request.action === 'DIAGNOSE') {
      const diag = runDiagnostics();
      sendResponse({ success: true, diagnostics: diag });
      return true;
    }

    if (request.action === 'GET_COURSE_INFO') {
      sendResponse(getCourseInfo());
      return true;
    }
  });
})();
