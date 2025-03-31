import os
import subprocess
import whisper
from moviepy import VideoFileClip, CompositeVideoClip, TextClip
from collections import Counter
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import threading
import queue
import tempfile
import shutil
import atexit
import matplotlib.font_manager as fm

class TempFileManager:
    """Gerenciador de arquivos temporários com limpeza automática"""
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="video_processor_")
        self.temp_files = []
        atexit.register(self.cleanup)
    
    def create_temp_file(self, suffix="", prefix="tmp"):
        """Cria um arquivo temporário gerenciado"""
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=self.temp_dir)
        os.close(fd)
        self.temp_files.append(path)
        return path
    
    def cleanup(self):
        """Remove todos os arquivos temporários e o diretório"""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Erro ao remover arquivo temporário {file_path}: {e}")
        
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            print(f"Erro ao remover diretório temporário {self.temp_dir}: {e}")


class VideoProcessor:
    def __init__(self, config, temp_manager):
        self.config = config
        self.temp_manager = temp_manager

    def find_interesting_segments(self, video_path):
        """Encontra segmentos interessantes baseado em análise de áudio"""
        try:
            temp_audio = self.temp_manager.create_temp_file(suffix=".wav", prefix="audio_")
            self._extract_audio_to_wav(video_path, temp_audio)
            
            audio = AudioSegment.from_wav(temp_audio)
            
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=self.config.get('min_silence_len', 1000),
                silence_thresh=self.config.get('silence_threshold', -40)
            )
            
            moments = []
            for start, end in nonsilent_ranges:
                margin = self.config.get('safety_margin', 500)
                start = max(0, (start - margin))
                end = min(len(audio), (end + margin))
                
                if end - start < 2:
                    continue
                    
                moments.append(start)
            
            if not moments:
                return self._fallback_segments(video_path)
            return moments
            
        except Exception as e:
            print(f"Erro ao analisar áudio: {e}")
            return self._fallback_segments(video_path)

    def _fallback_segments(self, video_path):
        """Método alternativo caso a análise de áudio falhe"""
        try:
            with VideoFileClip(video_path) as clip:
                return [i for i in range(0, int(clip.duration), self.config['clip_duration'])]
        except Exception as e:
            print(f"Erro no fallback: {e}")
            return [0]

    def create_clip(self, video_path, start_time, output_path):
        """Cria um subclip e o salva no caminho especificado."""
        try:
            command = [
                "ffmpeg",
                "-y",
                "-ss", str(start_time),
                "-i", video_path,
                "-t", str(self.config['clip_duration']),
                "-c:v", "libx264",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-movflags", "+faststart",
                output_path
            ]
            subprocess.run(command, check=True, timeout=300)
        except subprocess.CalledProcessError as e:
            print(f"Erro ao executar o comando ffmpeg: {e}")
            raise
        except subprocess.TimeoutExpired:
            print("Tempo limite excedido para o comando ffmpeg")
            raise

    def add_subtitles_to_video(self, video_path, output_path, segments, subtitle_config):
        """Adiciona legendas ao vídeo com configurações personalizadas."""
        try:
            with VideoFileClip(video_path) as video:
                font = subtitle_config.get('font', 'Arial')
                font_size = subtitle_config.get('font_size', 62)
                font_color = subtitle_config.get('font_color', 'yellow')
                stroke_color = subtitle_config.get('stroke_color', 'black')
                stroke_width = subtitle_config.get('stroke_width', 1.5)
                position = subtitle_config.get('position', 'bottom')

                subtitle_clips = []
                for segment in segments:
                    txt_clip = TextClip(
                        text=segment["text"],
                        font=font,
                        fontsize=font_size,
                        color=font_color,
                        stroke_color=stroke_color,
                        stroke_width=stroke_width,
                        size=(int(video.w * 0.9), None),
                        method='caption'
                    )
                    
                    if position == 'top':
                        pos = ('center', 50)
                    elif position == 'middle':
                        pos = ('center', 'center')
                    else:
                        pos = ('center', video.h - 100)
                        
                    subtitle_clip = txt_clip.set_start(segment["start"]).set_duration(segment["end"] - segment["start"])
                    subtitle_clip = subtitle_clip.set_position(pos)
                    subtitle_clips.append(subtitle_clip)

                final_video = CompositeVideoClip([video, *subtitle_clips])
                final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=video.fps)
        except Exception as e:
            print(f"Erro ao adicionar legendas: {e}")
            raise

    def _extract_audio_to_wav(self, video_path, temp_audio_path):
        """Extrai áudio do vídeo para arquivo WAV temporário"""
        try:
            command = [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                temp_audio_path
            ]
            subprocess.run(command, check=True, timeout=300)
        except subprocess.CalledProcessError as e:
            print(f"Erro ao extrair áudio: {e}")
            raise
        except subprocess.TimeoutExpired:
            print("Tempo limite excedido para extração de áudio")
            raise


class VideoProcessorApp:
    def __init__(self, root):
        self.root = root
        self._setup_ui()
        self._initialize_variables()
        
    def _setup_ui(self):
        """Configura a interface gráfica"""
        self.style = ttk.Style()
        self.style.configure('Font.TCombobox', font=('Arial', 10))
        self.root.title("Processador de Vídeo Inteligente")
        self.root.geometry("900x850")
        
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Widgets de entrada
        ttk.Label(main_frame, text="Vídeo de Entrada:").grid(row=0, column=0, sticky=tk.W)
        self.video_path_entry = ttk.Entry(main_frame, width=50)
        self.video_path_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(main_frame, text="Procurar", command=self._browse_video).grid(row=0, column=2)

        # Configurações básicas
        settings_frame = ttk.LabelFrame(main_frame, text="Configurações Básicas", padding=10)
        settings_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=5)

        ttk.Label(settings_frame, text="Adicionar legendas:").grid(row=1, column=0, sticky=tk.W)
        self.add_subtitles_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, variable=self.add_subtitles_var).grid(row=1, column=1, padx=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Modelo Whisper:").grid(row=0, column=0, sticky=tk.W)
        self.model_combo = ttk.Combobox(settings_frame, values=['tiny', 'base', 'small', 'medium', 'large'], 
                                      state="readonly")
        self.model_combo.set('medium')
        self.model_combo.grid(row=0, column=1, padx=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Duração do Clip (s):").grid(row=0, column=2, sticky=tk.W)
        self.duration_entry = ttk.Entry(settings_frame, width=8)
        self.duration_entry.insert(0, "45")
        self.duration_entry.grid(row=0, column=3, padx=5, sticky=tk.W)
        self.duration_entry.config(validate="key", 
            validatecommand=(self.duration_entry.register(self._validate_number), '%P'))

        # Configurações avançadas
        advanced_frame = ttk.LabelFrame(main_frame, text="Configurações Avançadas de Corte", padding=10)
        advanced_frame.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=5)

        self._create_slider(advanced_frame, "Limiar de Silêncio (dB):", 0, -60, -20, -40)
        self._create_slider(advanced_frame, "Duração Mínima (s):", 1, 1.0, 40.0, 1.0)
        self._create_slider(advanced_frame, "Margem Segurança (s):", 2, 0, 1.0, 0.5)

        # Configurações de legendas
        self.subtitle_frame = self._create_subtitle_settings(main_frame)
        self.subtitle_frame.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=5)

        # Área de log
        ttk.Label(main_frame, text="Log de Execução:").grid(row=5, column=0, sticky=tk.W)
        self.log_text = tk.Text(main_frame, height=15, width=70)
        self.log_text.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=10)

        # Botões de controle
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=10)
        
        self.process_btn = ttk.Button(btn_frame, text="Processar Vídeo", command=self._process_video)
        self.process_btn.pack(side=tk.LEFT, padx=5)

        self.preview_btn = ttk.Button(btn_frame, text="Pré-visualizar Último Clip", 
                                     command=self._preview_last_clip, state=tk.DISABLED)
        self.preview_btn.pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(btn_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.cancel_btn = ttk.Button(btn_frame, text="Cancelar", 
                                    command=self._cancel_processing, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)
        advanced_frame.columnconfigure(1, weight=1)
        self.subtitle_frame.columnconfigure(1, weight=1)

    def _initialize_variables(self):
        """Inicializa variáveis e gerenciadores"""
        self.temp_manager = TempFileManager()
        self.model = None
        self.progress_queue = queue.Queue()
        self.processing_thread = None
        self.stop_event = threading.Event()
        self.last_clip_path = None

    def _create_slider(self, parent, label_text, row, from_, to, initial):
        """Cria um slider com label e valor exibido"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W)
        slider = ttk.Scale(parent, from_=from_, to=to, value=initial)
        slider.grid(row=row, column=1, padx=5, sticky=tk.EW)
        value_label = ttk.Label(parent, text=str(initial))
        value_label.grid(row=row, column=2)
        slider.config(command=lambda v: value_label.config(text=f"{float(v):.1f}"))
        return slider

    def _create_subtitle_settings(self, parent):
        """Cria o frame de configurações de legendas"""
        frame = ttk.LabelFrame(parent, text="Configurações de Legendas", padding=10)
        
        # Configurações de fonte
        ttk.Label(frame, text="Fonte:").grid(row=0, column=0, sticky=tk.W)
        self.font_combo = ttk.Combobox(frame, state="readonly", style='Font.TCombobox')
        self.font_combo.grid(row=0, column=1, padx=5, sticky=tk.EW)
        self.font_combo.bind('<<ComboboxSelected>>', self._update_font_style)
        
        # Tamanho da fonte
        ttk.Label(frame, text="Tamanho:").grid(row=1, column=0, sticky=tk.W)
        self.font_size = ttk.Spinbox(frame, from_=8, to=120, width=5)
        self.font_size.set(62)
        self.font_size.grid(row=1, column=1, padx=5, sticky=tk.W)
        
        # Cores e posição
        ttk.Label(frame, text="Cor do texto:").grid(row=2, column=0, sticky=tk.W)
        self.font_color = ttk.Combobox(frame, values=['white', 'yellow', 'red', 'green', 'blue', 'black'], 
                                     state="readonly")
        self.font_color.set('yellow')
        self.font_color.grid(row=2, column=1, padx=5, sticky=tk.W)
        
        ttk.Label(frame, text="Cor do contorno:").grid(row=3, column=0, sticky=tk.W)
        self.stroke_color = ttk.Combobox(frame, values=['black', 'white', 'red', 'green', 'blue', 'none'], 
                                       state="readonly")
        self.stroke_color.set('black')
        self.stroke_color.grid(row=3, column=1, padx=5, sticky=tk.W)
        
        ttk.Label(frame, text="Posição:").grid(row=4, column=0, sticky=tk.W)
        self.sub_position = ttk.Combobox(frame, values=['top', 'middle', 'bottom'], state="readonly")
        self.sub_position.set('bottom')
        self.sub_position.grid(row=4, column=1, padx=5, sticky=tk.W)
        
        self._load_available_fonts()
        return frame

    def _load_available_fonts(self):
        """Carrega as fontes disponíveis no sistema"""
        try:
            fonts = list(set([f.name for f in fm.fontManager.ttflist]))
            self.font_combo['values'] = sorted(fonts)
            if 'Arial' in fonts:
                self.font_combo.set('Arial')
            elif fonts:
                self.font_combo.set(fonts[0])
            self._update_font_style()
        except Exception as e:
            print(f"Erro ao carregar fontes: {e}")
            self.font_combo['values'] = ['Arial']
            self.font_combo.set('Arial')
            self._update_font_style()

    def _update_font_style(self, event=None):
        """Atualiza o estilo da fonte no Combobox"""
        selected_font = self.font_combo.get()
        try:
            self.style.configure('Font.TCombobox', font=(selected_font, 10))
        except:
            self.style.configure('Font.TCombobox', font=('Arial', 10))
        self.font_combo.update()

    def _validate_number(self, value):
        """Valida se o valor é um número positivo"""
        return value.isdigit() and int(value) > 0 or value == ""

    def _browse_video(self):
        """Abre diálogo para selecionar arquivo de vídeo"""
        filepath = filedialog.askopenfilename(filetypes=[("Arquivos de Vídeo", "*.mp4 *.avi *.mov *.mkv")])
        if filepath:
            self.video_path_entry.delete(0, tk.END)
            self.video_path_entry.insert(0, filepath)

    def _log_message(self, message):
        """Adiciona mensagem ao log"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def _preview_last_clip(self):
        """Reproduz o último clip processado"""
        if self.last_clip_path and os.path.exists(self.last_clip_path):
            try:
                subprocess.Popen(["ffplay", "-autoexit", "-window_title", "Pré-visualização", self.last_clip_path])
            except Exception as e:
                self._log_message(f"Erro ao reproduzir pré-visualização: {e}")
        else:
            messagebox.showwarning("Aviso", "Nenhum clip disponível para pré-visualização")

    def _process_video(self):
        """Inicia o processamento do vídeo"""
        if self.processing_thread and self.processing_thread.is_alive():
            return

        video_path = self.video_path_entry.get()
        if not video_path:
            messagebox.showerror("Erro", "Selecione um arquivo de vídeo!")
            return

        settings = {
            'whisper_model': self.model_combo.get(),
            'clip_duration': int(self.duration_entry.get()),
            'temp_dir': os.path.join(os.getcwd(), "temp"),
            'silence_threshold': -40,
            'min_silence_len': 1.0,
            'safety_margin': 0.5,
            'add_subtitles': self.add_subtitles_var.get()
        }

        try:
            self.stop_event.clear()
            self.process_btn.config(state=tk.DISABLED)
            self.preview_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.progress['value'] = 0
            
            self.processing_thread = threading.Thread(
                target=self._run_processing, 
                args=(video_path, settings),
                daemon=True
            )
            self.processing_thread.start()
            
            self.root.after(100, self._update_progress)
            
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao iniciar processamento: {str(e)}")
            self._reset_interface()

    def _run_processing(self, video_path, settings):
        """Executa o processamento do vídeo em uma thread separada"""
        try:
            self.progress_queue.put(("log", "Iniciando processamento..."))
            self.progress_queue.put(("progress", 0))
            
            if settings['add_subtitles']:
                self.progress_queue.put(("log", "Carregando modelo Whisper..."))
                self.model = whisper.load_model(settings['whisper_model'])
                self.progress_queue.put(("log", f"Modelo {settings['whisper_model']} carregado com sucesso!"))
            
            processor = VideoProcessor(settings, self.temp_manager)
            
            video_dir = os.path.dirname(video_path)
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            output_dir = os.path.join(video_dir, "cortes_com_legendas" if settings['add_subtitles'] else "cortes_sem_legendas")
            os.makedirs(output_dir, exist_ok=True)

            self.progress_queue.put(("log", "Analisando vídeo para encontrar segmentos..."))
            moments = processor.find_interesting_segments(video_path)
            self.progress_queue.put(("log", f"Encontrados {len(moments)} segmentos interessantes"))
            
            total_clips = len(moments)
            for i, start_time in enumerate(moments):
                if self.stop_event.is_set():
                    self.progress_queue.put(("log", "Processamento cancelado pelo usuário"))
                    break
                
                progress = (i + 1) / total_clips * 100
                self.progress_queue.put(("progress", progress))
                self.progress_queue.put(("log", f"\nProcessando segmento {i+1}/{len(moments)} (início em {start_time:.2f}s)..."))
                
                clip_title = f"{video_name}_clip_{i + 1}"
                final_clip_path = os.path.join(output_dir, f"{clip_title}.mp4")
                processor.create_clip(video_path, start_time, final_clip_path)
                self.last_clip_path = final_clip_path
                
                if settings['add_subtitles']:
                    subtitle_config = {
                        'font': self.font_combo.get(),
                        'font_size': int(self.font_size.get()),
                        'font_color': self.font_color.get(),
                        'stroke_color': None if self.stroke_color.get() == 'none' else self.stroke_color.get(),
                        'stroke_width': 1.5,
                        'position': self.sub_position.get()
                    }
                    
                    temp_audio_path = self.temp_manager.create_temp_file(suffix=".wav", prefix=f"audio_{i}_")
                    processor._extract_audio_to_wav(final_clip_path, temp_audio_path)
                    
                    self.progress_queue.put(("log", "Transcrevendo áudio..."))
                    result = self.model.transcribe(temp_audio_path, language="pt", word_timestamps=True)
                    
                    relevant_segments = self._process_transcription_result(result, settings['clip_duration'])
                    
                    transcription_text = " ".join([seg["text"] for seg in relevant_segments])
                    video_title = self._extract_keywords(transcription_text)
                    self.progress_queue.put(("log", f"Título sugerido: {video_title}"))

                    temp_clip_with_subtitles = self.temp_manager.create_temp_file(suffix=".mp4", prefix=f"clip_{i}_subs_")
                    processor.add_subtitles_to_video(final_clip_path, temp_clip_with_subtitles, relevant_segments, subtitle_config)

                    final_clip_with_subtitles = os.path.join(output_dir, f"{video_title}_clip_{i + 1}.mp4")
                    self._restore_audio_format(final_clip_path, temp_clip_with_subtitles, final_clip_with_subtitles)
                    
                    os.remove(final_clip_path)
                    self.last_clip_path = final_clip_with_subtitles
                    self.progress_queue.put(("log", f"Clip {i+1} (com legendas) salvo em: {final_clip_with_subtitles}"))
                else:
                    self.progress_queue.put(("log", f"Clip {i+1} (sem legendas) salvo em: {final_clip_path}"))

            if not self.stop_event.is_set():
                self.progress_queue.put(("complete", None))
            
        except Exception as e:
            self.progress_queue.put(("error", str(e)))

    def _process_transcription_result(self, result, clip_duration):
        """Processa o resultado da transcrição para extrair segmentos relevantes"""
        relevant_segments = []
        current_speaker = None
        
        for segment in result["segments"]:
            text = segment["text"].strip()
            
            if len(text) < 3 or text in ["...", "[música]", "[risos]"]:
                continue
                
            if current_speaker is None or (segment["start"] - current_speaker["end"]) > 1.5:
                if current_speaker:
                    relevant_segments.append(current_speaker)
                current_speaker = {
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": text
                }
            else:
                current_speaker["end"] = segment["end"]
                current_speaker["text"] += " " + text
        
        if current_speaker:
            relevant_segments.append(current_speaker)
        
        if not relevant_segments:
            relevant_segments = [{
                "start": 0,
                "end": clip_duration,
                "text": "[Conteúdo não verbal]"
            }]
        
        return relevant_segments

    def _extract_keywords(self, text, num_keywords=3):
        """Extrai palavras-chave do texto"""
        words = re.findall(r'\w+', text.lower())
        stop_words = {'e', 'de', 'a', 'o', 'que', 'do', 'da', 'em', 'um', 'para', 'é', 'com', 'não', 'uma', 'os', 'no', 'se', 'na', 'por', 'mais', 'as', 'dos', 'como', 'mas', 'foi', 'ao', 'ele', 'das', 'tem', 'à', 'seu', 'sua', 'ou', 'ser', 'quando', 'muito', 'há', 'nos', 'já', 'está', 'eu', 'também', 'só', 'pelo', 'pela', 'até', 'isso', 'ela', 'entre', 'era', 'depois', 'sem', 'mesmo', 'aos', 'ter', 'seus', 'quem', 'nas', 'me', 'esse', 'eles', 'estão', 'você', 'tinha', 'foram', 'essa', 'num', 'nem', 'suas', 'meu', 'minha', 'têm', 'numa', 'pelos', 'elas', 'havia', 'seja', 'qual', 'será', 'nós', 'tenho', 'lhe', 'deles', 'essas', 'esses', 'pelas', 'este', 'fosse', 'dele', 'tu', 'te', 'vocês', 'vos', 'lhes', 'meus', 'minhas', 'teu', 'tua', 'teus', 'tuas', 'nosso', 'nossa', 'nossos', 'nossas', 'dela', 'delas', 'esta', 'estes', 'estas', 'aquele', 'aquela', 'aqueles', 'aquelas', 'isto', 'aquilo'}
        filtered_words = [word for word in words if word not in stop_words]
        most_common = Counter(filtered_words).most_common(num_keywords)
        keywords = [word for word, _ in most_common]
        return ' '.join(keywords).title()

    def _restore_audio_format(self, original_video_path, video_with_subtitles_path, final_output_path):
        """Restaura o formato original do áudio no vídeo com legendas"""
        try:
            command = [
                "ffmpeg",
                "-y",
                "-i", video_with_subtitles_path,
                "-i", original_video_path,
                "-c:v", "copy",
                "-c:a", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                final_output_path
            ]
            subprocess.run(command, check=True, timeout=300)
        except subprocess.CalledProcessError as e:
            print(f"Erro ao restaurar áudio: {e}")
            raise
        except subprocess.TimeoutExpired:
            print("Tempo limite excedido para restaurar áudio")
            raise

    def _update_progress(self):
        """Atualiza a interface com o progresso do processamento"""
        try:
            while True:
                msg_type, content = self.progress_queue.get_nowait()
                
                if msg_type == "log":
                    self._log_message(content)
                elif msg_type == "progress":
                    self.progress['value'] = content
                elif msg_type == "error":
                    messagebox.showerror("Erro", content)
                    self._reset_interface()
                elif msg_type == "complete":
                    messagebox.showinfo("Sucesso", "Processamento concluído com sucesso!")
                    self.preview_btn.config(state=tk.NORMAL)
                    self._reset_interface()
                
                self.root.update_idletasks()
                
        except queue.Empty:
            pass
        
        if self.processing_thread and self.processing_thread.is_alive():
            self.root.after(100, self._update_progress)
        else:
            self._reset_interface()

    def _reset_interface(self):
        """Restaura a interface para o estado inicial"""
        self.progress['value'] = 0
        self.process_btn.config(state=tk.NORMAL)
        self.preview_btn.config(state=tk.NORMAL if self.last_clip_path else tk.DISABLED)
        self.cancel_btn.config(state=tk.DISABLED)
        self.processing_thread = None

    def _cancel_processing(self):
        """Cancela o processamento em andamento"""
        if self.processing_thread and self.processing_thread.is_alive():
            self.stop_event.set()
            self._log_message("Cancelando processamento...")
            self.cancel_btn.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoProcessorApp(root)
    root.mainloop()
