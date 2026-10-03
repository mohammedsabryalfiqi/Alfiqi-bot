#!/usr/bin/env python3
"""
Alfiqi Bot Hosting Platform — نقطة الدخول.

شغّل المنصة باستخدام:
    python main.py

المنصة نفسها عبارة عن بوت تلجرام تحط توكنه في BOT_TOKEN وتحدد OWNER_ID،
ومن خلاله تضيف بوتات أخرى (تستضيفها) بمجرد إدخال توكناتها واختيار قالبها.
"""

from hostbot.main import main

if __name__ == "__main__":
    main()
