"""Host roster with an inline remove control for each guest."""

import streamlit as st

_ROSTER = st.components.v2.component(
    "thorajit_host_roster",
    html='<div class="roster-root"></div>',
    css="""
    .roster-root { font-family: Nunito, sans-serif; color: #603112; }
    .cue { margin: 0 0 .35rem; font-size: .85rem; color: #6b492d; }
    .columns { display: flex; gap: .75rem; overflow-x: auto; padding: .2rem; }
    .columns:focus-visible, button:focus-visible { outline: 3px solid #4a6414; outline-offset: 2px; }
    .column { flex: 1 0 100%; min-width: 0; }
    .multiple .column { flex-basis: calc(50% - .375rem); min-width: 11rem; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: .5rem;
      min-height: 3rem; border-bottom: 1px solid #dec49a; }
    .name { min-width: 0; overflow-wrap: anywhere; font-weight: 800; }
    button { flex: none; display: grid; place-items: center; width: 2.75rem; height: 2.75rem;
      border-radius: 50%; border: 2px solid #a36b32; background: #fff0d4; color: #603112;
      font-size: 1.5rem; font-weight: 900; cursor: pointer; }
    button:hover { background: #f7dfad; }
    """,
    js="""
    export default function ({ parentElement, data, setTriggerValue }) {
      const root = parentElement.querySelector('.roster-root');
      root.replaceChildren();
      const players = data.players || [];
      if (players.length > 5) {
        const cue = document.createElement('p');
        cue.className = 'cue'; cue.textContent = 'Scroll sideways to see all players →';
        root.append(cue);
      }
      const columns = document.createElement('div');
      columns.className = 'columns' + (players.length > 5 ? ' multiple' : '');
      columns.setAttribute('role', 'region');
      columns.setAttribute('aria-label', 'Players');
      columns.tabIndex = 0;
      for (let i = 0; i < players.length; i += 5) {
        const column = document.createElement('div');
        column.className = 'column'; column.setAttribute('role', 'list');
        for (const player of players.slice(i, i + 5)) {
          const row = document.createElement('div');
          row.className = 'row'; row.setAttribute('role', 'listitem');
          const name = document.createElement('span');
          name.className = 'name';
          name.textContent = [player.emoji, player.name + (player.host ? ' (Host) (You)' : '')].filter(Boolean).join(' ');
          row.append(name);
          if (!player.host) {
            const button = document.createElement('button');
            button.type = 'button'; button.textContent = '×';
            button.setAttribute('aria-label', `Remove ${player.name} from room`);
            button.onclick = () => setTriggerValue('remove', player.id);
            row.append(button);
          }
          column.append(row);
        }
        columns.append(column);
      }
      root.append(columns);
    }
    """,
)


def host_roster(players: list, *, host_id: str, key: str) -> str | None:
    result = _ROSTER(
        key=key,
        data={"players": [{"id": player.player_id, "name": player.name,
                           "emoji": getattr(player, "emoji", "") or "",
                           "host": player.player_id == host_id} for player in players]},
        on_remove_change=lambda: None,
        width="stretch",
    )
    return result.remove
