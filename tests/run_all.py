"""
مشغّل كل الاختبارات مرة واحدة:

    python tests/run_all.py

كل ملف اختبار بيشتغل في مجلد مؤقت مستقل (بدون أي اتصال بتيليجرام)،
فملفات الحالة (settings.json و غيرها) ما بتتكتبش جوه المستودع.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITES = ["test_format.py", "test_core.py", "test_ui.py", "test_batch2.py"]


def main() -> int:
    results = []
    for suite in SUITES:
        path = HERE / suite
        if not path.exists():
            continue
        print(f"\n{'=' * 60}\n▶ {suite}\n{'=' * 60}")
        proc = subprocess.run([sys.executable, str(path)], cwd="/tmp")
        results.append((suite, proc.returncode))

    print(f"\n{'=' * 60}\nالنتيجة النهائية\n{'=' * 60}")
    failed = 0
    for suite, code in results:
        print(f"{'✅' if code == 0 else '❌'} {suite}")
        failed += 1 if code else 0
    if failed:
        print(f"\n❌ {failed} من {len(results)} مجموعة فيها فشل")
        return 1
    print(f"\n🎉 كل المجموعات نجحت ({len(results)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
