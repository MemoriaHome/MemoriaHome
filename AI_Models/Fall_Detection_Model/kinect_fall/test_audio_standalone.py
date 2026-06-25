import os
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['SSL_CERT_FILE']      = ''
os.environ['CURL_CA_BUNDLE']     = ''
os.environ['HF_HUB_DISABLE_SSL_VERIFICATION'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import time
import threading
import numpy as np


class MockConfig:
    device_id              = "audio-test"
    patient_id             = "test-patient"
    room                   = "Test Room"
    backend_url            = "https://localhost:3000"
    kinect_audio_device    = "NUI Sens"
    audio_threshold        = 0.35
    audio_cooldown_seconds = 3
    audio_block_seconds    = 0.25
    distress_window_seconds = 2.0
    distress_hop_seconds   = 0.5
    stutter_window_seconds = 3.0
    stutter_hop_seconds    = 1.5
    audio_debug            = True
    stutter_log_only       = True


from modules.audio_detection import AudioDetectionModule
from modules.speech_analysis import SpeechAnalysisModule


def main():
    print("=" * 50)
    print("AUDIO DETECTION STANDALONE TEST")
    print("=" * 50)

    config = MockConfig()
    audio  = AudioDetectionModule(config)
    speech = SpeechAnalysisModule(config)
    audio.set_speech_module(speech)

    # List available microphones
    audio.list_microphones()

    # Start audio modules
    speech.start()
    audio.start()

    print("\nCommands:")
    print("  1 — Test scream.wav")
    print("  2 — Test groan.wav")
    print("  3 — Test stutter.wav")
    print("  4 — Test live mic (speak/make noise)")
    print("  q — Quit")
    print("\nWatching for distress sounds and stuttering...\n")

    # Monitor loop — prints state every second
    def monitor_loop():
        while True:
            state = audio.get_state()

            # Emotion / distress
            if state['detected']:
                print(f"\n>>> EMOTION DISTRESS: "
                      f"{state['level'].upper()} — "
                      f"{state['label']} "
                      f"({state['confidence']:.0%} confidence)\n")

            # Stuttering
            if state['stutter_detected']:
                concern = " ⚠️ CONCERNING" if state['stutter_concern'] else ""
                print(f"\n>>> STUTTER DETECTED: "
                      f"{state['stutter_type']} "
                      f"({state['stutter_score']:.0%})"
                      f"{concern}\n")

            speech_state = speech.get_state()
            if speech_state['keyword_detected']:
                print(f"\n>>> DISTRESS WORD: "
                      f"{speech_state['keyword']} "
                      f"(heard: {speech_state['transcript']})\n")
            elif speech_state['transcript']:
                print(f"\n>>> SPEECH HEARD: "
                      f"{speech_state['transcript']}\n")

            time.sleep(0.5)

    monitor_thread = threading.Thread(
        target=monitor_loop,
        daemon=True
    )
    monitor_thread.start()

    # Input loop
    while True:
        try:
            cmd = input()

            if cmd == '1':
                print("\n--- Testing scream.wav ---")
                threading.Thread(
                    target=audio.test_with_file,
                    args=("test_sounds/scream.wav",),
                    daemon=True
                ).start()

            elif cmd == '2':
                print("\n--- Testing groan.wav ---")
                threading.Thread(
                    target=audio.test_with_file,
                    args=("test_sounds/groan.wav",),
                    daemon=True
                ).start()

            elif cmd == '3':
                print("\n--- Testing stutter.wav ---")
                threading.Thread(
                    target=audio.test_with_file,
                    args=("test_sounds/stutter.wav", False),
                    daemon=True
                ).start()

            elif cmd == '4':
                print("\n--- Live mic active ---")
                print("Speak or make noise near the microphone...")

            elif cmd == 'h':
                # Print stutter history
                state = audio.get_state()
                history = state['stutter_history']
                if history:
                    print("\n--- Stutter History ---")
                    for entry in history:
                        ts = time.strftime(
                            '%H:%M:%S',
                            time.localtime(entry['timestamp'])
                        )
                        print(f"  [{ts}] {entry['type']} "
                              f"({entry['score']:.0%})")
                else:
                    print("\nNo stutter history yet")

            elif cmd == 's':
                # Print full current state
                state = audio.get_state()
                print("\n--- Current State ---")
                print(f"  Distress detected : {state['detected']}")
                print(f"  Emotion label     : {state['label']}")
                print(f"  Emotion level     : {state['level']}")
                print(f"  Emotion confidence: {state['confidence']:.0%}")
                print(f"  Stutter detected  : {state['stutter_detected']}")
                print(f"  Stutter type      : {state['stutter_type']}")
                print(f"  Stutter score     : {state['stutter_score']:.0%}")
                print(f"  Concerning        : {state['stutter_concern']}")
                speech_state = speech.get_state()
                print(f"  Speech active     : {speech_state['speech_active']}")
                print(f"  Keyword detected  : {speech_state['keyword_detected']}")
                print(f"  Keyword           : {speech_state['keyword']}")
                print(f"  Transcript        : {speech_state['transcript']}")
                print()

            elif cmd == 'q':
                break

            elif cmd == '?':
                print("\nCommands:")
                print("  1 — Test scream.wav")
                print("  2 — Test groan.wav")
                print("  3 — Test stutter.wav")
                print("  4 — Live mic mode")
                print("  h — Show stutter history")
                print("  s — Show full current state")
                print("  ? — Show this help")
                print("  q — Quit")

        except KeyboardInterrupt:
            break

    audio.stop()
    speech.stop()
    print("\nTest complete.")


if __name__ == "__main__":
    main()
