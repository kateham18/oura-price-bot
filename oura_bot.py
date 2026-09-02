import os
import requests

topic = os.environ["NTFY_TOPIC"]

requests.post(
    f"https://ntfy.sh/{topic}",
    data="Your Oura price bot is working! 💍".encode("utf-8"),
    headers={
        "Title": "Oura Bot Test",
        "Priority": "high",
        "Tags": "white_check_mark"
    },
)

print("Notification sent.")
