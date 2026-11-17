"""Збереження сцен на телефоні: <id>.json (опис сцени) і <id>.png (мініатюра)."""
import json
import os
import time
import uuid


class ProjectStore:
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def _json(self, pid):
        return os.path.join(self.folder, f"{pid}.json")

    def thumb(self, pid):
        return os.path.join(self.folder, f"{pid}.png")

    @staticmethod
    def new_id():
        return time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]

    def list(self):
        out = []
        for name in os.listdir(self.folder):
            if not name.endswith(".json"):
                continue
            pid = name[:-5]
            path = self._json(pid)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            out.append({"id": pid, "title": data.get("title") or "Сцена",
                        "mtime": os.path.getmtime(path), "thumb": self.thumb(pid)})
        out.sort(key=lambda p: p["mtime"], reverse=True)
        return out

    def load(self, pid):
        with open(self._json(pid), encoding="utf-8") as f:
            return json.load(f)

    def save(self, pid, scene):
        tmp = self._json(pid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(scene, f, ensure_ascii=False)
        os.replace(tmp, self._json(pid))

    def delete(self, pid):
        for p in (self._json(pid), self.thumb(pid)):
            try:
                os.remove(p)
            except OSError:
                pass
