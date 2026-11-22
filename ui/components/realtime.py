"""Browser credential storage and payload-free push notifications."""
import streamlit as st


_component = st.components.v2.component(
    "room_realtime",
    html="<span></span>",
    js=r"""
const instances = new WeakMap();
export default function({data, parentElement, setStateValue, setTriggerValue}) {
  let instance = instances.get(parentElement);
  if (!instance) {
    instance = {socket: null, timer: null, token: null, closed: false};
    instances.set(parentElement, instance);
    // Action buttons can take time to rerun. Show feedback immediately,
    // then clear it when Streamlit's running indicator disappears.
    let pending = null;
    let seenRunning = false;
    let fallback = null;
    let maximum = null;
    const clearPending = () => {
      clearTimeout(fallback);
      clearTimeout(maximum);
      if (pending) {
        pending.classList.remove('thorajit-processing');
        pending.removeAttribute('aria-busy');
      }
      pending = null;
      seenRunning = false;
    };
    const isRunning = () => !!document.querySelector('[data-testid="stStatusWidgetRunningIcon"]');
    const observer = new MutationObserver(() => {
      if (!pending) return;
      if (!pending.isConnected) { clearPending(); return; }
      if (isRunning()) seenRunning = true;
      else if (seenRunning) clearPending();
    });
    observer.observe(document.body, {childList: true, subtree: true});
    const handleClick = event => {
      const button = event.target.closest?.('div.stButton > button');
      if (!button || button.disabled || button.classList.contains('thorajit-processing')) return;
      // Panel toggles are immediate UI controls; popover triggers are also
      // excluded because they are not Streamlit action buttons.
      if (button.closest('.st-key-game_panel_buttons, [class*="_close_scores"], [class*="_close_settings"]')) return;
      clearPending();
      pending = button;
      button.classList.add('thorajit-processing');
      button.setAttribute('aria-busy', 'true');
      seenRunning = isRunning();
      // No running indicator means an immediate interaction or validation.
      fallback = setTimeout(() => { if (!seenRunning && !isRunning()) clearPending(); }, 1500);
      maximum = setTimeout(clearPending, 120000);
    };
    document.addEventListener('click', handleClick, true);
    instance.cleanupFeedback = () => {
      document.removeEventListener('click', handleClick, true);
      observer.disconnect();
      clearPending();
    };
    let stored = null;
    try { stored = localStorage.getItem('thorajit.reconnect'); } catch (_) {}
    setStateValue('credential', stored || '');
  }
  if (data.clear) {
    try { localStorage.removeItem('thorajit.reconnect'); } catch (_) {}
  }
  if (data.token) {
    try { localStorage.setItem('thorajit.reconnect', data.token); } catch (_) {}
  }
  const token = data.clear ? null : data.token;
  function connect() {
    if (instance.closed || !instance.token) return;
    const prefix = window.location.pathname.replace(/\/$/, '');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}${prefix}/api/realtime`);
    instance.socket = ws;
    ws.onopen = () => ws.send(instance.token);
    ws.onmessage = event => {
      if (event.data === 'sync') setTriggerValue('changed', Date.now());
      if (event.data === 'invalid') {
        instance.token = null;
        setTriggerValue('invalid', true);
      }
    };
    ws.onclose = () => {
      if (!instance.closed && instance.socket === ws && instance.token)
        instance.timer = setTimeout(connect, 1000);
    };
  }
  if (instance.token !== token) {
    instance.token = token;
    clearTimeout(instance.timer);
    if (instance.socket) { instance.socket.onclose = null; instance.socket.close(); }
    if (token) connect();
  }
  return () => {
    instance.closed = true;
    clearTimeout(instance.timer);
    if (instance.socket) { instance.socket.onclose = null; instance.socket.close(); }
    instance.cleanupFeedback();
    instances.delete(parentElement);
  };
}
""",
)


def render_realtime(token=None, clear=False):
    return _component(key="room_realtime", data={"token": token, "clear": clear},
                      on_credential_change=lambda: None, on_changed_change=lambda: None,
                      on_invalid_change=lambda: None)
