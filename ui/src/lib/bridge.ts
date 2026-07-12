export interface GameInfo {
  id: string;
  name: string;
  description: string;
  capabilities: Record<string, boolean>;
}

// Detect if running inside Tauri or a plain browser
const isTauri = "__TAURI_INTERNALS__" in window;

const API_BASE = "http://localhost:9876";

/** Fetch registered games. Works in Tauri (invoke) or browser (fetch). */
export async function fetchGames(): Promise<GameInfo[]> {
  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    const raw: string = await invoke("list_games");
    const lines = raw.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('{"type":')) {
        return JSON.parse(trimmed).data;
      }
    }
    return [];
  }

  // Browser mode: call Python HTTP API
  const res = await fetch(`${API_BASE}/api/games`);
  return res.json();
}

/** Start the translation pipeline for a game. */
export async function startGame(
  gameId: string,
  monitor: number = 1,
): Promise<string> {
  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("start_game", { gameId, monitor });
  }

  // Browser mode
  const res = await fetch(`${API_BASE}/api/start/${gameId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monitor }),
  });
  const data = await res.json();
  return JSON.stringify(data);
}

/** Stop the translation pipeline. */
export async function stopGame(): Promise<string> {
  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke("stop_game");
  }

  const res = await fetch(`${API_BASE}/api/stop`, { method: "POST" });
  const data = await res.json();
  return JSON.stringify(data);
}

/** Check engine status. */
export async function engineStatus(): Promise<{
  running: boolean;
  game: string | null;
}> {
  if (isTauri) {
    return { running: false, game: null };
  }

  const res = await fetch(`${API_BASE}/api/status`);
  return res.json();
}
