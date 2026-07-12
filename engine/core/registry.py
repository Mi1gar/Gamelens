from typing import Dict, Type, List, Optional
from .interfaces import BaseGameAdapter

class GameRegistry:
    """
    Central repository for all supported Game Adapters.
    """
    _adapters: Dict[str, Type[BaseGameAdapter]] = {}

    @classmethod
    def register(cls, adapter_cls: Type[BaseGameAdapter]):
        """
        Decorator to register a Game Adapter.
        """
        # Ensure the class has the required metadata
        if hasattr(adapter_cls, 'GAME_ID'):
             key = adapter_cls.GAME_ID
             cls._adapters[key] = adapter_cls
             print(f"[Registry] Registered Game: {key}")
        else:
             print(f"[Registry] Failed to register {adapter_cls.__name__}: Missing GAME_ID")
        return adapter_cls

    @classmethod
    def get_all_games(cls) -> List[dict]:
        """
        Returns a lightweight list of available games for the UI.
        """
        games = []
        for gid, a_cls in cls._adapters.items():
            games.append({
                "id": gid,
                "name": getattr(a_cls, "DISPLAY_NAME", "Unknown"),
                "description": getattr(a_cls, "DESCRIPTION", ""),
                "capabilities": getattr(a_cls, "CAPABILITIES", {}),
            })
        return games

    @classmethod
    def get_adapter(cls, game_id: str) -> Optional[BaseGameAdapter]:
        if game_id in cls._adapters:
            # Instantiate using the registered class
            return cls._adapters[game_id]()
        return None
