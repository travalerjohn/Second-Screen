"""
Second Screen Controller - Controle de Segunda Tela
Gerencia fotos, vídeos e imagens fixadas em segunda tela (fullscreen).
Tela principal: controles completos.
Segunda tela: exibição fullscreen.
Player nativo de vídeo (PyAV + sounddevice), sem VLC.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os
import sys
import json

NATIVE_PLAYER_ERROR = None
try:
    from native_video_player import NativeVideoPlayer
except Exception as e:
    NativeVideoPlayer = None
    NATIVE_PLAYER_ERROR = str(e)


class SecondScreenWindow:
    """Janela da segunda tela (fullscreen)."""

    def __init__(self, root):
        self.root = root
        self.root.title("Second Screen")
        self.root.configure(bg="black")

        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.current_image = None
        self.player = None
        self._volume = 80
        self._frame_job = None

    def go_fullscreen(self, monitor_index=1):
        """Coloca a janela em fullscreen no monitor especificado."""
        self.root.update_idletasks()

        monitors = self.get_monitors()
        if monitor_index < len(monitors):
            x, y, w, h = monitors[monitor_index]
        else:
            x, y, w, h = monitors[0]

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.overrideredirect(True)
        self.root.lift()
        self.root.focus_force()

    def get_monitors(self):
        """Retorna geometria dos monitores disponíveis."""
        monitors = []
        try:
            if sys.platform == "win32":
                import ctypes

                class RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", ctypes.c_long),
                        ("top", ctypes.c_long),
                        ("right", ctypes.c_long),
                        ("bottom", ctypes.c_long),
                    ]

                user32 = ctypes.windll.user32
                EnumDisplayMonitors = user32.EnumDisplayMonitors
                monitors_data = []

                MONITORENUMPROC = ctypes.WINFUNCTYPE(
                    ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.POINTER(RECT), ctypes.c_void_p
                )

                def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                    r = lprcMonitor.contents
                    monitors_data.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
                    return 1

                EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)

                for m in monitors_data:
                    monitors.append(m)
            else:
                monitors.append((0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
        except Exception:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            monitors.append((0, 0, w, h))

        if not monitors:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            monitors.append((0, 0, w, h))

        return monitors

    def _canvas_size(self):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if w <= 1:
            w = self.root.winfo_screenwidth()
        if h <= 1:
            h = self.root.winfo_screenheight()
        return max(w, 1), max(h, 1)

    def _fit_image(self, img, screen_w, screen_h):
        img_ratio = img.width / img.height
        screen_ratio = screen_w / screen_h

        if img_ratio > screen_ratio:
            new_w = screen_w
            new_h = max(1, int(screen_w / img_ratio))
        else:
            new_h = screen_h
            new_w = max(1, int(screen_h * img_ratio))

        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        return img.resize((new_w, new_h), Image.LANCZOS)

    def show_image(self, image_path):
        """Exibe uma imagem fullscreen na segunda tela."""
        self._stop_video()
        screen_w, screen_h = self._canvas_size()

        try:
            img = Image.open(image_path)
            img = self._fit_image(img, screen_w, screen_h)
            self.current_image = ImageTk.PhotoImage(img)

            self.canvas.delete("all")
            self.canvas.create_image(
                screen_w // 2, screen_h // 2,
                image=self.current_image, anchor=tk.CENTER
            )
        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(
                screen_w // 2, screen_h // 2,
                text=f"Erro ao carregar imagem:\n{e}",
                fill="white", font=("Arial", 24), justify=tk.CENTER
            )

    def show_color(self, color):
        """Exibe uma cor sólida na segunda tela."""
        self._stop_video()
        self.canvas.delete("all")
        self.canvas.configure(bg=color)
        self.canvas.create_text(
            self.root.winfo_width() // 2,
            self.root.winfo_height() // 2,
            text="", fill="white"
        )

    def show_text(self, text, font_size=72, color="white", bg="black"):
        """Exibe texto na segunda tela."""
        self._stop_video()
        self.canvas.delete("all")
        self.canvas.configure(bg=bg)
        self.canvas.create_text(
            self.root.winfo_width() // 2,
            self.root.winfo_height() // 2,
            text=text, fill=color,
            font=("Arial", font_size), justify=tk.CENTER
        )

    def play_video(self, video_path):
        """Reproduz vídeo fullscreen na segunda tela (player nativo, sem VLC)."""
        self._stop_video()

        if NativeVideoPlayer is None:
            screen_w, screen_h = self._canvas_size()
            self.canvas.delete("all")
            self.canvas.create_text(
                screen_w // 2, screen_h // 2,
                text="Dependências do player de vídeo ausentes.\n"
                     "Instale com:\npip install av sounddevice numpy",
                fill="red", font=("Arial", 24), justify=tk.CENTER
            )
            return False

        try:
            player = NativeVideoPlayer()
            player.set_volume(self._volume)
            player.load(video_path)
            player.play()
            self.player = player
            self._schedule_video_frames()
            return True
        except Exception as e:
            self.player = None
            screen_w, screen_h = self._canvas_size()
            self.canvas.delete("all")
            self.canvas.create_text(
                screen_w // 2, screen_h // 2,
                text=f"Erro ao reproduzir vídeo:\n{e}",
                fill="red", font=("Arial", 24), justify=tk.CENTER
            )
            return False

    def _schedule_video_frames(self):
        if self.player is None:
            return
        if not self.player.is_playing():
            self._frame_job = None
            return

        img = self.player.get_ready_frame()
        if img is not None:
            self._draw_video_frame(img)

        self._frame_job = self.root.after(16, self._schedule_video_frames)

    def _draw_video_frame(self, img):
        screen_w, screen_h = self._canvas_size()
        try:
            fitted = self._fit_image(img, screen_w, screen_h)
            self.current_image = ImageTk.PhotoImage(fitted)
            self.canvas.delete("all")
            self.canvas.create_image(
                screen_w // 2, screen_h // 2,
                image=self.current_image, anchor=tk.CENTER
            )
        except Exception:
            pass

    def pause_video(self):
        if self.player:
            self.player.pause()

    def resume_video(self):
        if self.player:
            self.player.resume()
            if self.player.is_playing() and not self._frame_job:
                self._schedule_video_frames()

    def stop_video(self):
        self._stop_video()
        self.canvas.delete("all")

    def _stop_video(self):
        if self._frame_job is not None:
            try:
                self.root.after_cancel(self._frame_job)
            except Exception:
                pass
            self._frame_job = None

        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
            self.player = None
        self.canvas.configure(bg="black")

    def has_video(self):
        return self.player is not None and self.player.is_loaded()

    def is_video_playing(self):
        if self.player:
            return self.player.is_playing()
        return False

    def is_video_paused(self):
        if self.player:
            return self.player.is_paused()
        return False

    def is_video_finished(self):
        if self.player:
            return self.player.is_finished()
        return False

    def get_video_position(self):
        if self.player:
            return self.player.get_position_fraction()
        return 0

    def get_video_times(self):
        """Retorna (tempo_atual_seg, duracao_seg)."""
        if self.player and self.player.is_loaded():
            return self.player.get_position(), self.player.get_duration()
        return 0.0, 0.0

    def set_video_position(self, pos):
        if self.player:
            self.player.seek_fraction(pos)

    def set_volume(self, volume):
        """Define volume do vídeo (0-100)."""
        self._volume = max(0, min(100, int(volume)))
        if self.player:
            self.player.set_volume(self._volume)

    def get_volume(self):
        """Retorna volume atual do vídeo (0-100)."""
        return self._volume

    def toggle_fullscreen(self):
        if self.root.attributes("-fullscreen"):
            self.root.attributes("-fullscreen", False)
        else:
            self.root.attributes("-fullscreen", True)


class ControlPanel:
    """Painel de controle principal (primeira tela)."""

    def __init__(self, root):
        self.root = root
        self.root.title("Second Screen Controller")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        self.second_screen = None
        self.current_media_type = None  # "image", "video", "color", "text", "fixed"
        self.current_file = None
        self.is_paused = False
        self.slideshow_active = False
        self.slideshow_images = []
        self.slideshow_index = 0
        self.slideshow_interval = 5  # segundos
        self.fixed_image_path = None
        self._updating_progress = False
        self._seek_job = None
        self._pending_seek = None

        # Estilo
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self._setup_ui()
        self._detect_monitors()

        # Carrega config salva
        self._load_config()

    def _setup_ui(self):
        """Monta a interface de controle."""

        # === HEADER ===
        header = ttk.Frame(self.root, padding=10)
        header.pack(fill=tk.X)

        ttk.Label(header, text="📺 Second Screen Controller",
                  font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)

        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(header, textvariable=self.monitor_var,
                                          state="readonly", width=20)
        self.monitor_combo.pack(side=tk.RIGHT, padx=5)
        ttk.Label(header, text="Monitor:").pack(side=tk.RIGHT)

        # === BOTÕES PRINCIPAIS ===
        btn_frame = ttk.Frame(self.root, padding=10)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="🖼 Abrir Imagem",
                   command=self._open_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🎬 Abrir Vídeo",
                   command=self._open_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📌 Imagem Fixa",
                   command=self._open_fixed_image).pack(side=tk.LEFT, padx=5)

        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(btn_frame, text="📺 Abrir Segunda Tela",
                   command=self._open_second_screen).pack(side=tk.LEFT, padx=5)

        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(btn_frame, text="🔢 Identificar Telas",
                   command=self._identify_screens).pack(side=tk.LEFT, padx=5)

        # === CONTROLES DE VÍDEO ===
        self.video_controls = ttk.LabelFrame(self.root, text="Controles de Vídeo", padding=10)
        self.video_controls.pack(fill=tk.X, padx=10, pady=5)

        ctrl_row1 = ttk.Frame(self.video_controls)
        ctrl_row1.pack(fill=tk.X, pady=2)

        self.btn_play = ttk.Button(ctrl_row1, text="▶ Play", command=self._play)
        self.btn_play.pack(side=tk.LEFT, padx=5)

        self.btn_pause = ttk.Button(ctrl_row1, text="⏸ Pausar", command=self._pause)
        self.btn_pause.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(ctrl_row1, text="⏹ Parar", command=self._stop)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        ttk.Separator(ctrl_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(ctrl_row1, text="⏮ Início", command=self._video_beginning).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_row1, text="⏭ Fim", command=self._video_end).pack(side=tk.LEFT, padx=5)

        # Volume
        ctrl_row_vol = ttk.Frame(self.video_controls)
        ctrl_row_vol.pack(fill=tk.X, pady=2)

        ttk.Label(ctrl_row_vol, text="Volume:").pack(side=tk.LEFT)
        self.volume_var = tk.IntVar(value=80)
        self.volume_scale = ttk.Scale(ctrl_row_vol, from_=0, to=100,
                                       variable=self.volume_var,
                                       command=self._on_volume_change, length=150)
        self.volume_scale.pack(side=tk.LEFT, padx=5)
        self.volume_label = ttk.Label(ctrl_row_vol, text="80%")
        self.volume_label.pack(side=tk.LEFT, padx=2)

        # Barra de progresso
        ctrl_row2 = ttk.Frame(self.video_controls)
        ctrl_row2.pack(fill=tk.X, pady=5)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Scale(ctrl_row2, from_=0, to=100,
                                      variable=self.progress_var,
                                      command=self._on_progress_change)
        self.progress_bar.pack(fill=tk.X, padx=5)

        self.time_label = ttk.Label(ctrl_row2, text="00:00 / 00:00")
        self.time_label.pack(side=tk.RIGHT, padx=5)

        # === SLIDESHOW ===
        self.slideshow_frame = ttk.LabelFrame(self.root, text="Slideshow", padding=10)
        self.slideshow_frame.pack(fill=tk.X, padx=10, pady=5)

        slide_row = ttk.Frame(self.slideshow_frame)
        slide_row.pack(fill=tk.X)

        ttk.Button(slide_row, text="📁 Selecionar Pasta",
                   command=self._select_slideshow_folder).pack(side=tk.LEFT, padx=5)

        self.btn_slideshow_start = ttk.Button(slide_row, text="▶ Iniciar Slideshow",
                                               command=self._toggle_slideshow)
        self.btn_slideshow_start.pack(side=tk.LEFT, padx=5)

        ttk.Label(slide_row, text="Intervalo (seg):").pack(side=tk.LEFT, padx=(20, 5))
        self.interval_var = tk.IntVar(value=5)
        self.interval_spin = ttk.Spinbox(slide_row, from_=1, to=60,
                                         textvariable=self.interval_var, width=5)
        self.interval_spin.pack(side=tk.LEFT, padx=5)

        self.slide_status = ttk.Label(self.slideshow_frame, text="Nenhuma pasta selecionada")
        self.slide_status.pack(anchor=tk.W, pady=(5, 0))

        # === TEXTO / COR ===
        extras_frame = ttk.LabelFrame(self.root, text="Extras", padding=10)
        extras_frame.pack(fill=tk.X, padx=10, pady=5)

        extras_row = ttk.Frame(extras_frame)
        extras_row.pack(fill=tk.X)

        ttk.Label(extras_row, text="Texto:").pack(side=tk.LEFT)
        self.text_var = tk.StringVar()
        ttk.Entry(extras_row, textvariable=self.text_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Button(extras_row, text="Mostrar Texto", command=self._show_text).pack(side=tk.LEFT, padx=5)

        ttk.Separator(extras_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Label(extras_row, text="Cor:").pack(side=tk.LEFT)
        self.color_var = tk.StringVar(value="#000000")
        self.color_entry = ttk.Entry(extras_row, textvariable=self.color_var, width=10)
        self.color_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(extras_row, text="Aplicar Cor", command=self._show_color).pack(side=tk.LEFT, padx=5)
        ttk.Button(extras_row, text="🎨", command=self._pick_color, width=3).pack(side=tk.LEFT, padx=2)

        # === SEÇÃO IMAGEM FIXA ===
        self.fixed_frame = ttk.LabelFrame(self.root, text="Imagem Fixa na Segunda Tela", padding=10)
        self.fixed_frame.pack(fill=tk.X, padx=10, pady=5)

        fixed_row = ttk.Frame(self.fixed_frame)
        fixed_row.pack(fill=tk.X)

        self.fixed_status = ttk.Label(fixed_row, text="Nenhuma imagem fixa definida")
        self.fixed_status.pack(side=tk.LEFT, padx=5)

        ttk.Button(fixed_row, text="Ativar Fixa",
                   command=self._activate_fixed).pack(side=tk.RIGHT, padx=5)
        ttk.Button(fixed_row, text="Desativar Fixa",
                   command=self._deactivate_fixed).pack(side=tk.RIGHT, padx=5)

        # === MONITOR STATUS ===
        status_frame = ttk.Frame(self.root, padding=10)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_label = ttk.Label(status_frame, text="Segunda tela: Desconectada",
                                       font=("Segoe UI", 10))
        self.status_label.pack(side=tk.LEFT)

        self.message_label = ttk.Label(status_frame, text="",
                                        font=("Segoe UI", 9), foreground="#e67e22")
        self.message_label.pack(side=tk.LEFT, padx=20)

        self.info_label = ttk.Label(status_frame, text="",
                                     font=("Segoe UI", 9), foreground="gray")
        self.info_label.pack(side=tk.RIGHT)

        # self.credit_label = ttk.Label(status_frame, text="by travalerjohn",
        #                                font=("Segoe UI", 7), foreground="")
        # self.credit_label.pack(side=tk.RIGHT, padx=10)
        # self.credit_label.bind("<Enter>", lambda e: self.credit_label.configure(foreground="gray"))
        # self.credit_label.bind("<Leave>", lambda e: self.credit_label.configure(foreground=""))

        # === ATUALIZAÇÃO PERIÓDICA ===
        self._update_progress()

    def _detect_monitors(self):
        """Detecta monitores disponíveis."""
        if self.second_screen:
            monitors = self.second_screen.get_monitors()
        else:
            # Cria janela temporária para detectar
            temp = tk.Toplevel()
            temp.withdraw()
            monitors_info = SecondScreenWindow(temp)
            monitors = monitors_info.get_monitors()
            temp.destroy()

        monitor_names = []
        for i, (x, y, w, h) in enumerate(monitors):
            monitor_names.append(f"Monitor {i + 1} ({w}x{h})")

        self.monitor_combo["values"] = monitor_names
        if monitor_names:
            # Seleciona o segundo monitor por padrão, se existir
            if len(monitor_names) > 1:
                self.monitor_combo.current(1)
            else:
                self.monitor_combo.current(0)

    def _open_second_screen(self):
        """Abre a janela da segunda tela."""
        if self.second_screen and self.second_screen.root.winfo_exists():
            self.second_screen.root.lift()
            return

        second_root = tk.Toplevel(self.root)
        self.second_screen = SecondScreenWindow(second_root)

        monitor_idx = self.monitor_combo.current()
        self.second_screen.go_fullscreen(monitor_idx)

        self.status_label.configure(text="Segunda tela: Conectada ✅")

        # Se tinha imagem fixa, mostra
        if self.fixed_image_path:
            self.second_screen.show_image(self.fixed_image_path)

    def _open_image(self):
        """Abre e exibe uma imagem na segunda tela."""
        path = filedialog.askopenfilename(
            title="Selecionar Imagem",
            filetypes=[
                ("Imagens", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp"),
                ("Todos", "*.*")
            ]
        )
        if path:
            self._set_media("image", path)

    def _open_video(self):
        """Abre e reproduz um vídeo na segunda tela."""
        path = filedialog.askopenfilename(
            title="Selecionar Vídeo",
            filetypes=[
                ("Vídeos", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v"),
                ("Todos", "*.*")
            ]
        )
        if path:
            self._set_media("video", path)

    def _open_fixed_image(self):
        """Seleciona imagem que ficará fixa na segunda tela."""
        path = filedialog.askopenfilename(
            title="Selecionar Imagem Fixa",
            filetypes=[
                ("Imagens", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp"),
                ("Todos", "*.*")
            ]
        )
        if path:
            self.fixed_image_path = path
            name = os.path.basename(path)
            self.fixed_status.configure(text=f"Fixa: {name}")

            # Se a segunda tela estiver aberta e não estiver com vídeo, aplica
            if self.second_screen and self.second_screen.root.winfo_exists():
                if not self.second_screen.is_video_playing() and not self.second_screen.is_video_paused():
                    self.second_screen.show_image(path)

            self._save_config()

    def _activate_fixed(self):
        """Ativa a imagem fixa na segunda tela."""
        if self.fixed_image_path and self.second_screen and self.second_screen.root.winfo_exists():
            self.second_screen.show_image(self.fixed_image_path)
        elif not self.fixed_image_path:
            self._show_message("Selecione uma imagem fixa primeiro!")

    def _deactivate_fixed(self):
        """Desativa a imagem fixa."""
        self.fixed_image_path = None
        self.fixed_status.configure(text="Nenhuma imagem fixa definida")
        self._save_config()

        if self.second_screen and self.second_screen.root.winfo_exists():
            self.second_screen.show_color("black")

    def _set_media(self, media_type, path):
        """Define e exibe o mídia na segunda tela."""
        self.current_media_type = media_type
        self.current_file = path
        self.is_paused = False

        if not self.second_screen or not self.second_screen.root.winfo_exists():
            self._open_second_screen()

        if media_type == "image":
            self.second_screen.show_image(path)
            name = os.path.basename(path)
            self.info_label.configure(text=f"Imagem: {name}")

        elif media_type == "video":
            success = self.second_screen.play_video(path)
            if success:
                name = os.path.basename(path)
                self.info_label.configure(text=f"Vídeo: {name}")

    def _play(self):
        """Play no vídeo."""
        if self.second_screen and self.second_screen.root.winfo_exists():
            if self.is_paused:
                self.second_screen.resume_video()
                self.is_paused = False
            elif self.current_file and self.current_media_type == "video":
                self._set_media("video", self.current_file)

    def _pause(self):
        """Pausa o vídeo."""
        if self.second_screen and self.second_screen.root.winfo_exists():
            if self.second_screen.is_video_playing():
                self.second_screen.pause_video()
                self.is_paused = True
            elif self.is_paused:
                self.second_screen.resume_video()
                self.is_paused = False

    def _stop(self):
        """Para o vídeo."""
        if self.second_screen and self.second_screen.root.winfo_exists():
            self.second_screen.stop_video()
            self.current_media_type = None
            self.current_file = None
            self.is_paused = False
            self.progress_var.set(0)
            self.time_label.configure(text="00:00 / 00:00")
            self.info_label.configure(text="")
            self._restore_fixed_image()

    def _video_beginning(self):
        """Volta o vídeo ao início."""
        if self.second_screen:
            self.second_screen.set_video_position(0)

    def _video_end(self):
        """Vai ao fim do vídeo."""
        if self.second_screen:
            self.second_screen.set_video_position(0.99)

    def _on_progress_change(self, value):
        """Muda posição do vídeo ao arrastar a barra (com debounce)."""
        if self._updating_progress:
            return
        if not (
            self.second_screen
            and self.current_media_type == "video"
            and self.second_screen.has_video()
        ):
            return

        self._pending_seek = float(value) / 100.0
        if self._seek_job is None:
            self._seek_job = self.root.after(200, self._apply_pending_seek)

    def _apply_pending_seek(self):
        self._seek_job = None
        if self._pending_seek is None:
            return
        pos = self._pending_seek
        self._pending_seek = None
        if self.second_screen and self.second_screen.has_video():
            self.second_screen.set_video_position(pos)

    def _select_slideshow_folder(self):
        """Seleciona pasta para slideshow."""
        folder = filedialog.askdirectory(title="Selecionar Pasta de Imagens")
        if folder:
            exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp")
            images = sorted([
                os.path.join(folder, f) for f in os.listdir(folder)
                if f.lower().endswith(exts)
            ])
            if images:
                self.slideshow_images = images
                self.slideshow_index = 0
                self.slide_status.configure(
                    text=f"Pasta: {os.path.basename(folder)} | {len(images)} imagens encontradas"
                )
            else:
                self.slideshow_images = []
                self._show_message("Nenhuma imagem encontrada na pasta!")

    def _toggle_slideshow(self):
        """Inicia/para o slideshow."""
        if self.slideshow_active:
            self.slideshow_active = False
            self.btn_slideshow_start.configure(text="▶ Iniciar Slideshow")
            self.slide_status.configure(text=f"Slideshow pausado na imagem {self.slideshow_index + 1}")
            self._restore_fixed_image()
        else:
            if not self.slideshow_images:
                self._show_message("Selecione uma pasta primeiro!")
                return
            self.slideshow_active = True
            self.slideshow_interval = self.interval_var.get()
            self.btn_slideshow_start.configure(text="⏸ Pausar Slideshow")
            self._run_slideshow()

    def _run_slideshow(self):
        """Executa o slideshow."""
        if not self.slideshow_active:
            return

        if not self.second_screen or not self.second_screen.root.winfo_exists():
            self._open_second_screen()

        if self.slideshow_images:
            img_path = self.slideshow_images[self.slideshow_index]
            self.second_screen.show_image(img_path)
            self.slide_status.configure(
                text=f"Slideshow: {self.slideshow_index + 1}/{len(self.slideshow_images)} - {os.path.basename(img_path)}"
            )
            self.slideshow_index = (self.slideshow_index + 1) % len(self.slideshow_images)

            self.root.after(self.slideshow_interval * 1000, self._run_slideshow)

    def _show_text(self):
        """Exibe texto na segunda tela."""
        text = self.text_var.get().strip()
        if not text:
            self._show_message("Digite um texto!")
            return

        if not self.second_screen or not self.second_screen.root.winfo_exists():
            self._open_second_screen()

        self.second_screen.show_text(text)
        self.info_label.configure(text=f"Texto: {text}")

    def _show_color(self):
        """Exibe cor na segunda tela."""
        color = self.color_var.get().strip()
        if not color:
            return

        if not self.second_screen or not self.second_screen.root.winfo_exists():
            self._open_second_screen()

        self.second_screen.show_color(color)
        self.info_label.configure(text=f"Cor: {color}")

    def _pick_color(self):
        """Abre seletor de cor."""
        from tkinter import colorchooser
        color = colorchooser.askcolor(title="Escolher Cor")
        if color[1]:
            self.color_var.set(color[1])
            self._show_color()

    def _on_volume_change(self, value):
        """Muda volume do vídeo."""
        vol = int(float(value))
        self.volume_label.configure(text=f"{vol}%")
        if self.second_screen and self.second_screen.root.winfo_exists():
            self.second_screen.set_volume(vol)

    def _identify_screens(self):
        """Mostra número grande em cada monitor por 5 segundos."""
        temp = tk.Toplevel()
        temp.withdraw()
        temp_obj = SecondScreenWindow(temp)
        monitors = temp_obj.get_monitors()
        temp.destroy()

        for i, (x, y, w, h) in enumerate(monitors):
            win = tk.Toplevel(self.root)
            win.configure(bg="black")
            win.overrideredirect(True)
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.lift()
            win.focus_force()

            canvas = tk.Canvas(win, bg="black", highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_text(
                w // 2, h // 2,
                text=str(i + 1),
                fill="white",
                font=("Arial", min(w, h) // 4, "bold")
            )

            win.after(5000, win.destroy)

    def _update_progress(self):
        """Atualiza barra de progresso e tempo do vídeo."""
        if (
            self.second_screen
            and self.current_media_type == "video"
            and self.second_screen.has_video()
        ):
            pos = self.second_screen.get_video_position()
            self._updating_progress = True
            try:
                self.progress_var.set(pos * 100)
            finally:
                self._updating_progress = False

            current, total = self.second_screen.get_video_times()
            if total > 0:
                cur_m, cur_s = divmod(int(current), 60)
                tot_m, tot_s = divmod(int(total), 60)
                self.time_label.configure(
                    text=f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}"
                )

            finished = self.second_screen.is_video_finished()
            if finished and not self.is_paused:
                self.current_media_type = None
                self.current_file = None
                self.progress_var.set(0)
                self.time_label.configure(text="00:00 / 00:00")
                self.info_label.configure(text="Vídeo finalizado")
                self._restore_fixed_image()

        self.root.after(500, self._update_progress)

    def _show_message(self, text, duration=3000):
        """Mostra mensagem na barra inferior por X milissegundos."""
        self.message_label.configure(text=text)
        self.root.after(duration, lambda: self.message_label.configure(text=""))

    def _restore_fixed_image(self):
        """Restaura a imagem fixa na segunda tela se existir."""
        if self.fixed_image_path and self.second_screen and self.second_screen.root.winfo_exists():
            self.second_screen.show_image(self.fixed_image_path)
            name = os.path.basename(self.fixed_image_path)
            self.info_label.configure(text=f"Fixa: {name}")

    def _get_config_path(self):
        """Retorna caminho da pasta de configuração."""
        if sys.platform == "win32":
            app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            app_data = os.path.expanduser("~")
        config_dir = os.path.join(app_data, "SecondScreen")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config.json")

    def _save_config(self):
        """Salva configurações."""
        config = {
            "fixed_image": self.fixed_image_path,
            "slideshow_interval": self.interval_var.get()
        }
        try:
            with open(self._get_config_path(), "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_config(self):
        """Carrega configurações salvas."""
        try:
            config_path = self._get_config_path()
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.fixed_image_path = config.get("fixed_image")
                self.interval_var.set(config.get("slideshow_interval", 5))

                if self.fixed_image_path and os.path.exists(self.fixed_image_path):
                    name = os.path.basename(self.fixed_image_path)
                    self.fixed_status.configure(text=f"Fixa: {name}")
        except Exception:
            pass


def main():
    root = tk.Tk()
    root.withdraw()
    try:
        if NATIVE_PLAYER_ERROR:
            messagebox.showwarning(
                "Player de vídeo indisponível",
                "O player nativo de vídeo não pôde ser carregado:\n\n"
                f"{NATIVE_PLAYER_ERROR}\n\n"
                "Imagens e textos ainda funcionam.\n"
                "Para vídeo/áudio, instale as dependências:\n"
                "pip install -r requirements.txt"
            )

        app = ControlPanel(root)
        root.deiconify()
        root.mainloop()
    except Exception as e:
        root.deiconify()
        messagebox.showerror("Erro", f"Ocorreu um erro:\n\n{e}")
        print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()
        input("Pressione Enter para fechar...")


if __name__ == "__main__":
    main()
