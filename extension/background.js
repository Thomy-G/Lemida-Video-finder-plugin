// background.js - Lemida Video Finder Service Worker

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'UPDATE_BADGE') {
    const count = message.count;
    const tabId = sender.tab ? sender.tab.id : undefined;
    if (tabId !== undefined) {
      if (count > 0) {
        chrome.action.setBadgeText({ text: count.toString(), tabId });
        chrome.action.setBadgeBackgroundColor({ color: '#00a86b', tabId });
      } else {
        chrome.action.setBadgeText({ text: '', tabId });
      }
    }
    sendResponse({ success: true });
    return true;
  }

  if (message.action === 'GET_COOKIES') {
    chrome.cookies.getAll({ domain: 'lemida.biu.ac.il' }, (cookies) => {
      const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');
      const moodleSession = cookies.find(c => c.name === 'MoodleSession')?.value || '';
      sendResponse({
        cookies,
        cookieHeader,
        moodleSession
      });
    });
    return true; // Keep channel open for async response
  }
});
