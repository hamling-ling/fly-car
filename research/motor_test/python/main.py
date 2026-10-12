from arduino.app_utils import App, Bridge
import time

def loop():
    try:
        print("Moving forward...")
        Bridge.call("setMotorSpeed", 255, 255)
        time.sleep(3)

        print("Rotate right...")
        Bridge.call("setMotorSpeed", 255, -255)
        time.sleep(3)

        print("Rotate left...")
        Bridge.call("setMotorSpeed", -255, 255)
        time.sleep(3)

        print("Moving backward...")
        Bridge.call("setMotorSpeed", -255, -255)
        time.sleep(3)

        print("Stopping...")
        Bridge.call("setMotorSpeed", 0, 0)

        # 一度だけ動かして終わりにする場合
        time.sleep(10)   # またはここで break したい場合はフラグで制御

    except Exception as e:
        print(f"Error: {e}")
        Bridge.call("setMotorSpeed", 0, 0)

App.run(user_loop=loop)
