// Built with emoji-mart 5.6.0 and @emoji-mart/data 1.2.1; see EMOJI-LICENSE.
import { Picker } from "emoji-mart";
import data from "@emoji-mart/data";

export default function ({ parentElement, data: props, setStateValue }) {
  const root = parentElement.querySelector(".emoji-root");
  if (!root) return;
  root.replaceChildren();
  const button = document.createElement("button");
  button.type = "button";
  button.className = "emoji-trigger";
  button.textContent = props.value ? `${props.value}  Change emoji` : "Choose your emoji";
  button.setAttribute("aria-expanded", "false");
  const message = document.createElement("div");
  message.className = "emoji-message";
  message.setAttribute("role", "status");
  const holder = document.createElement("div");
  const normalize = (emoji) => emoji.normalize("NFC").replaceAll("\ufe0f", "");
  const takenEmoji = new Set((props.taken || []).map(normalize));
  let draft = props.value || "";
  let observer;
  holder.hidden = true;
  root.append(button, message, holder);
  button.onclick = () => {
    if (!holder.hidden) {
      holder.querySelector(".emoji-cancel")?.click();
      return;
    }
    holder.hidden = !holder.hidden;
    button.setAttribute("aria-expanded", String(!holder.hidden));
    if (!holder.hidden && !holder.firstChild) {
      const selection = document.createElement("p");
      selection.className = "emoji-selection";
      selection.setAttribute("aria-live", "polite");
      const actions = document.createElement("div");
      actions.className = "emoji-actions";
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.className = "emoji-confirm";
      confirm.textContent = "Use this emoji";
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "emoji-cancel";
      cancel.textContent = "Cancel";
      const updateSelection = () => {
        selection.textContent = draft ? `Selected: ${draft}` : "Choose an emoji to continue.";
        confirm.disabled = !draft || takenEmoji.has(normalize(draft));
      };
      confirm.onclick = () => setStateValue("value", draft);
      cancel.onclick = () => {
        draft = props.value || "";
        message.textContent = "";
        updateSelection();
        holder.hidden = true;
        button.setAttribute("aria-expanded", "false");
        button.focus();
      };
      const picker = new Picker({
        data,
        theme: "light",
        previewPosition: "none",
        skinTonePosition: "search",
        onEmojiSelect: (item) => {
          if (takenEmoji.has(normalize(item.native))) {
            message.textContent = "That emoji is already taken. Choose another.";
            return;
          }
          message.textContent = "";
          draft = item.native;
          updateSelection();
        },
      });
      actions.append(confirm, cancel);
      holder.append(picker, selection, actions);
      updateSelection();
      const shadow = picker.shadowRoot;
      if (shadow) {
        const style = document.createElement("style");
        style.textContent = `
          button[data-thorajit-taken] { position: relative; opacity: .55; }
          button[data-thorajit-taken]::after { content: "Taken"; position: absolute; bottom: 0;
            left: 0; right: 0; color: #fff; background: #704022; border-radius: 5px;
            font: 700 8px/1.3 sans-serif; text-align: center; }
        `;
        shadow.append(style);
        const markTaken = () => {
          shadow.querySelectorAll("button[aria-label]").forEach((item) => {
            const label = item.getAttribute("aria-label") || "";
            const native = label.replace(/, taken$/, "");
            const isTaken = takenEmoji.has(normalize(native));
            if (isTaken) {
              if (label !== `${native}, taken`) item.setAttribute("aria-label", `${native}, taken`);
              if (item.getAttribute("aria-disabled") !== "true") item.setAttribute("aria-disabled", "true");
              item.setAttribute("data-thorajit-taken", "");
              item.title = `${item.title.replace(/ — taken$/, "")} — taken`;
            } else if (item.hasAttribute("data-thorajit-taken")) {
              item.removeAttribute("data-thorajit-taken");
              item.removeAttribute("aria-disabled");
              item.title = item.title.replace(/ — taken$/, "");
            }
          });
        };
        observer = new MutationObserver(markTaken);
        observer.observe(shadow, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-label"] });
        markTaken();
      }
    }
  };
  return () => observer?.disconnect();
}
