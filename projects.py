"""Збереження мультиків на телефоні.

projects/<id>/project.json — опис (сцени, герої, репліки)
projects/<id>/thumb.png    — мініатюра
projects/<id>/voices/      — записані голоси
projects/<id>/music/       — фонова музика
projects/<id>/video.mp4    — останнє зібране відео
"""
import copy
import json
import os
import shutil
import time
import uuid


class ProjectStore:
    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    @staticmethod
    def new_id():
        return time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]

    def dir(self, pid):
        d = os.path.join(self.folder, pid)
        os.makedirs(d, exist_ok=True)
        return d

    def sub(self, pid, name):
        d = os.path.join(self.dir(pid), name)
        os.makedirs(d, exist_ok=True)
        return d

    def thumb(self, pid):
        return os.path.join(self.dir(pid), "thumb.png")

    def video(self, pid):
        return os.path.join(self.dir(pid), "video.mp4")

    def _json(self, pid):
        return os.path.join(self.folder, pid, "project.json")

    # ------------------------------------------------------------ перехід із версії 1
    def migrate_v1(self, converter):
        """Старі файли <id>.json (одна сцена) -> папки проєктів."""
        for name in list(os.listdir(self.folder)):
            path = os.path.join(self.folder, name)
            if not (name.endswith(".json") and os.path.isfile(path)):
                continue
            pid = name[:-5]
            try:
                with open(path, encoding="utf-8") as f:
                    old = json.load(f)
                self.save(pid, converter(old))
                png = path[:-5] + ".png"
                if os.path.exists(png):
                    shutil.move(png, self.thumb(pid))
                os.remove(path)
            except (OSError, ValueError, KeyError):
                continue

    # ------------------------------------------------------------ список і файли
    def list(self):
        out = []
        for pid in os.listdir(self.folder):
            path = self._json(pid)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            out.append({"id": pid, "title": data.get("title") or "Мультик",
                        "scenes": len(data.get("scenes", [])),
                        "mtime": os.path.getmtime(path), "thumb": self.thumb(pid),
                        "has_video": os.path.exists(self.video(pid))})
        out.sort(key=lambda p: p["mtime"], reverse=True)
        return out

    def load(self, pid):
        with open(self._json(pid), encoding="utf-8") as f:
            return json.load(f)

    def save(self, pid, project):
        self.dir(pid)
        tmp = self._json(pid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(project, f, ensure_ascii=False)
        os.replace(tmp, self._json(pid))

    def delete(self, pid):
        shutil.rmtree(os.path.join(self.folder, pid), ignore_errors=True)

    def duplicate(self, pid):
        new = self.new_id()
        src = os.path.join(self.folder, pid)
        dst = os.path.join(self.folder, new)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("video.mp4"))
        data = self.load(new)
        data = copy.deepcopy(data)
        data["title"] = (data.get("title") or "Мультик") + " (копія)"
        self.save(new, data)
        return new

    def rename(self, pid, title):
        data = self.load(pid)
        data["title"] = title
        self.save(pid, data)
