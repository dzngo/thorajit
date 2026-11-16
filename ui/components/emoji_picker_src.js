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
  let observer;
  holder.hidden = true;
  root.append(button, message, holder);
  button.onclick = () => {
    holder.hidden = !holder.hidden;
    button.setAttribute("aria-expanded", String(!holder.hidden));
    if (holder.hidden) message.textContent = "";
    if (!holder.hidden && !holder.firstChild) {
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
          holder.hidden = true;
          button.setAttribute("aria-expanded", "false");
          button.textContent = `${item.native}  Change emoji`;
          button.focus();
          setStateValue("value", item.native);
        },
      });
      holder.append(picker);
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
