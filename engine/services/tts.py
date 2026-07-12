import time
import threading
import queue
from typing import Optional

class TTSService:
    def __init__(self, voice_model: str = "tr_voice_low_quality"):
        self.voice_model = voice_model
        print(f"[TTSService] Loading voice model {voice_model}...")
        time.sleep(0.5)
        
        # Audio Queue for asynchronous playback
        self._audio_queue = queue.Queue()
        self._is_running = True
        self._playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self._playback_thread.start()
        
        print("[TTSService] Service Ready (Async Mode).")

    def speak(self, text: str) -> float:
        """
        Generates audio and queues it for playback.
        Returns the time taken to GENERATE the audio (latency metric), NOT playback duration.
        """
        start_gen = time.time()
        
        # Simulate generation time (CPU bound part)
        time.sleep(0.15) 
        
        # In real impl, we would generate bytes here, then push bytes to queue
        # For mock, we just push the text to simulate "playing" this text
        self._audio_queue.put(text)
        
        return (time.time() - start_gen) * 1000

    def _playback_worker(self):
        """
        Consumes the queue and plays audio sequentially.
        """
        while self._is_running:
            try:
                text_to_play = self._audio_queue.get(timeout=1.0)
                # Simulate Playback (blocking usually, but in thread it's fine)
                # print(f"🔊 [AUDIO START] '{text_to_play}'")
                # Simulate length of audio
                time.sleep(len(text_to_play) * 0.05) 
                # print(f"🔊 [AUDIO END]")
                self._audio_queue.task_done()
            except queue.Empty:
                continue

    def stop(self):
        self._is_running = False
        if self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1.0)
