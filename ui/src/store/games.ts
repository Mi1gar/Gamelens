import { create } from "zustand";
import { fetchGames, startGame, stopGame, type GameInfo } from "../lib/bridge";

interface GamesState {
  games: GameInfo[];
  loading: boolean;
  error: string | null;
  activeGame: string | null;
  engineStatus: "idle" | "starting" | "running" | "error";

  loadGames: () => Promise<void>;
  launchGame: (gameId: string, monitor?: number) => Promise<void>;
  stopEngine: () => Promise<void>;
}

export const useGamesStore = create<GamesState>((set, get) => ({
  games: [],
  loading: false,
  error: null,
  activeGame: null,
  engineStatus: "idle",

  loadGames: async () => {
    if (get().games.length > 0) return; // already loaded
    set({ loading: true, error: null });
    try {
      const games = await fetchGames();
      set({ games, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  launchGame: async (gameId: string, monitor: number = 1) => {
    set({ engineStatus: "starting", activeGame: gameId });
    try {
      await startGame(gameId, monitor);
      set({ engineStatus: "running" });
    } catch (e) {
      set({ engineStatus: "error", error: String(e) });
    }
  },

  stopEngine: async () => {
    try {
      await stopGame();
    } catch (e) {
      // ignore — API may be unreachable if engine crashed
    }
    set({ engineStatus: "idle", activeGame: null });
  },
}));
