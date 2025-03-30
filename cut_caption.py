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
import time

class VideoProcessor:
    def __init__(self, config):
        self.config = config
        if not os.path.exists(self.config['temp_dir']):
            os.makedirs(self.config['temp_dir'])

    def find_interesting_segments(self, video_path):
        """Encontra segmentos interessantes baseado em análise de áudio"""
        try:
            # Extrair áudio temporário
            temp_audio = os.path.join(self.config['temp_dir'], "temp_audio.wav")
            extract_audio_to_wav(video_path, temp_audio)
            
            # Carregar arquivo de áudio
            audio = AudioSegment.from_wav(temp_audio)
            
            # Detectar partes não silenciosas
            nonsilent_ranges = detect_nonsilent(
                audio,
                min_silence_len=self.config.get('min_silence_len', 1000),
                silence_thresh=self.config.get('silence_threshold', -40)
            )
            
            # Converter para momentos de corte
            moments = []
            for start, end in nonsilent_ranges:
                # Adicionar margem de segurança
                margin = self.config.get('safety_margin', 500)
                start = max(0, (start - margin) / 1000)
                end = min(len(audio), (end + margin) / 1000)
                
                # Se o segmento for muito curto, pular
                if end - start < 2:  # Menos de 2 segundos
                    continue
                    
                moments.append(start)
            
            os.remove(temp_audio)
            if not moments:  # Se não encontrou nada, usar fallback
                return self.fallback_segments(video_path)
            return moments
            
        except Exception as e:
            print(f"Erro ao analisar áudio: {e}")
            return self.fallback_segments(video_path)

    def fallback_segments(self, video_path):
        """Método alternativo caso a análise de áudio falhe"""
        with VideoFileClip(video_path) as clip:
            return [i for i in range(0, int(clip.duration), self.config['clip_duration'])]

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
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Erro ao executar o comando ffmpeg: {e}")
            raise

    def add_subtitles_to_video(self, video_path, output_path, segments):
        """Adiciona legendas ao vídeo."""
        video = VideoFileClip(video_path)
        font_path = r"C:\Windows\Fonts\arial.ttf"

        subtitle_clips = []
        for segment in segments:
            subtitle_clip = TextClip(
                text=segment["text"],
                font=font_path,
                font_size=62,
                stroke_color='black',
                color='yellow',
                size=(int(video.w * 0.9), None),
                method='caption'
            ).set_position(('center', 'bottom')).set_start(segment["start"]).set_duration(segment["end"] - segment["start"])
            subtitle_clips.append(subtitle_clip)

        final_video = CompositeVideoClip([video, *subtitle_clips])
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=video.fps)

def extract_audio_to_wav(video_path, temp_audio_path):
    """Extrai o áudio do vídeo e o converte para WAV."""
    command = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        temp_audio_path
    ]
    subprocess.run(command, check=True)

def restore_audio_format(original_video_path, video_with_subtitles_path, final_output_path):
    """Restaura o formato original do áudio no vídeo final."""
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
    subprocess.run(command, check=True)

def extract_keywords(transcription_text, num_keywords=3):
    """Extrai palavras-chave do texto transcrito."""
    words = re.findall(r'\w+', transcription_text.lower())
    stop_words = {'e', 'de', 'a', 'o', 'que', 'do', 'da', 'em', 'um', 'para', 'é', 'com', 'não', 'uma', 'os', 'no', 'se', 'na', 'por', 'mais', 'as', 'dos', 'como', 'mas', 'foi', 'ao', 'ele', 'das', 'tem', 'à', 'seu', 'sua', 'ou', 'ser', 'quando', 'muito', 'há', 'nos', 'já', 'está', 'eu', 'também', 'só', 'pelo', 'pela', 'até', 'isso', 'ela', 'entre', 'era', 'depois', 'sem', 'mesmo', 'aos', 'ter', 'seus', 'quem', 'nas', 'me', 'esse', 'eles', 'estão', 'você', 'tinha', 'foram', 'essa', 'num', 'nem', 'suas', 'meu', 'minha', 'têm', 'numa', 'pelos', 'elas', 'havia', 'seja', 'qual', 'será', 'nós', 'tenho', 'lhe', 'deles', 'essas', 'esses', 'pelas', 'este', 'fosse', 'dele', 'tu', 'te', 'vocês', 'vos', 'lhes', 'meus', 'minhas', 'teu', 'tua', 'teus', 'tuas', 'nosso', 'nossa', 'nossos', 'nossas', 'dela', 'delas', 'esta', 'estes', 'estas', 'aquele', 'aquela', 'aqueles', 'aquelas', 'isto', 'aquilo'}
    filtered_words = [word for word in words if word not in stop_words]
    most_common = Counter(filtered_words).most_common(num_keywords)
    keywords = [word for word, _ in most_common]
    return ' '.join(keywords).title()

class VideoProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Processador de Vídeo Inteligente")
        self.root.geometry("900x750")
        
        self.settings = {
            'whisper_model': 'medium',
            'clip_duration': 45,
            'temp_dir': os.path.join(os.getcwd(), "temp"),
            'silence_threshold': -40,
            'min_silence_len': 1000,
            'safety_margin': 500,
            'add_subtitles': True
        }
        
        self.available_models = ['tiny', 'base', 'small', 'medium', 'large']
        self.model = None
        self.progress_queue = queue.Queue()
        self.processing_thread = None
        self.stop_event = threading.Event()
        self.last_clip_path = None
        
        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Seção de arquivo de vídeo
        ttk.Label(main_frame, text="Vídeo de Entrada:").grid(row=0, column=0, sticky=tk.W)
        self.video_path_entry = ttk.Entry(main_frame, width=50)
        self.video_path_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Button(main_frame, text="Procurar", command=self.browse_video).grid(row=0, column=2)

        # Seção de diretório temporário
        ttk.Label(main_frame, text="Diretório Temporário:").grid(row=1, column=0, sticky=tk.W)
        self.temp_dir_entry = ttk.Entry(main_frame, width=50)
        self.temp_dir_entry.insert(0, self.settings['temp_dir'])
        self.temp_dir_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Button(main_frame, text="Procurar", command=self.browse_temp_dir).grid(row=1, column=2)

        # Seção de configurações básicas
        settings_frame = ttk.LabelFrame(main_frame, text="Configurações Básicas", padding=10)
        settings_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=5)

        ttk.Label(settings_frame, text="Adicionar legendas:").grid(row=1, column=0, sticky=tk.W)
        self.add_subtitles_var = tk.BooleanVar(value=True)
        self.subtitles_check = ttk.Checkbutton(settings_frame, variable=self.add_subtitles_var)
        self.subtitles_check.grid(row=1, column=1, padx=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Modelo Whisper:").grid(row=0, column=0, sticky=tk.W)
        self.model_combo = ttk.Combobox(settings_frame, values=self.available_models, state="readonly")
        self.model_combo.set(self.settings['whisper_model'])
        self.model_combo.grid(row=0, column=1, padx=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Duração do Clip (s):").grid(row=0, column=2, sticky=tk.W)
        self.duration_entry = ttk.Entry(settings_frame, width=8)
        self.duration_entry.insert(0, str(self.settings['clip_duration']))
        self.duration_entry.grid(row=0, column=3, padx=5, sticky=tk.W)
        self.duration_entry.config(validate="key", 
            validatecommand=(self.duration_entry.register(self.validate_number), '%P'))

        # Seção de configurações avançadas
        advanced_frame = ttk.LabelFrame(main_frame, text="Configurações Avançadas de Corte", padding=10)
        advanced_frame.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=5)

        ttk.Label(advanced_frame, text="Limiar de Silêncio (dB):").grid(row=0, column=0, sticky=tk.W)
        self.silence_thresh_slider = ttk.Scale(advanced_frame, from_=-60, to=-20, value=self.settings['silence_threshold'])
        self.silence_thresh_slider.grid(row=0, column=1, padx=5, sticky=tk.EW)
        self.silence_thresh_value = ttk.Label(advanced_frame, text=str(self.settings['silence_threshold']))
        self.silence_thresh_value.grid(row=0, column=2)
        self.silence_thresh_slider.config(command=lambda v: self.silence_thresh_value.config(text=f"{float(v):.0f}"))

        ttk.Label(advanced_frame, text="Duração Mínima (ms):").grid(row=1, column=0, sticky=tk.W)
        self.min_silence_slider = ttk.Scale(advanced_frame, from_=500, to=3000, value=self.settings['min_silence_len'])
        self.min_silence_slider.grid(row=1, column=1, padx=5, sticky=tk.EW)
        self.min_silence_value = ttk.Label(advanced_frame, text=str(self.settings['min_silence_len']))
        self.min_silence_value.grid(row=1, column=2)
        self.min_silence_slider.config(command=lambda v: self.min_silence_value.config(text=f"{float(v):.0f}"))

        ttk.Label(advanced_frame, text="Margem Segurança (ms):").grid(row=2, column=0, sticky=tk.W)
        self.margin_slider = ttk.Scale(advanced_frame, from_=0, to=1000, value=self.settings['safety_margin'])
        self.margin_slider.grid(row=2, column=1, padx=5, sticky=tk.EW)
        self.margin_value = ttk.Label(advanced_frame, text=str(self.settings['safety_margin']))
        self.margin_value.grid(row=2, column=2)
        self.margin_slider.config(command=lambda v: self.margin_value.config(text=f"{float(v):.0f}"))

        # Área de log
        ttk.Label(main_frame, text="Log de Execução:").grid(row=4, column=0, sticky=tk.W)
        self.log_text = tk.Text(main_frame, height=15, width=70)
        self.log_text.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=10)

        # Botões
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=10)
        
        self.process_btn = ttk.Button(btn_frame, text="Processar Vídeo", command=self.process_video)
        self.process_btn.pack(side=tk.LEFT, padx=5)

        self.preview_btn = ttk.Button(btn_frame, text="Pré-visualizar Último Clip", command=self.preview_last_clip, state=tk.DISABLED)
        self.preview_btn.pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(btn_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.cancel_btn = ttk.Button(btn_frame, text="Cancelar", command=self.cancel_processing, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)
        advanced_frame.columnconfigure(1, weight=1)

    def validate_number(self, value):
        if value.isdigit() and int(value) > 0:
            return True
        elif value == "":
            return True
        return False

    def browse_video(self):
        filepath = filedialog.askopenfilename(filetypes=[("Arquivos de Vídeo", "*.mp4 *.avi *.mov *.mkv")])
        if filepath:
            self.video_path_entry.delete(0, tk.END)
            self.video_path_entry.insert(0, filepath)

    def browse_temp_dir(self):
        dirpath = filedialog.askdirectory()
        if dirpath:
            self.temp_dir_entry.delete(0, tk.END)
            self.temp_dir_entry.insert(0, dirpath)

    def log_message(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def preview_last_clip(self):
        if self.last_clip_path and os.path.exists(self.last_clip_path):
            try:
                subprocess.Popen(["ffplay", "-autoexit", "-window_title", "Pré-visualização", self.last_clip_path])
            except Exception as e:
                self.log_message(f"Erro ao reproduzir pré-visualização: {e}")
        else:
            messagebox.showwarning("Aviso", "Nenhum clip disponível para pré-visualização")

    def process_video(self):
        if self.processing_thread and self.processing_thread.is_alive():
            return

        self.settings['add_subtitles'] = self.add_subtitles_var.get()
        video_path = self.video_path_entry.get()
        self.settings.update({
            'whisper_model': self.model_combo.get(),
            'clip_duration': int(self.duration_entry.get()),
            'temp_dir': self.temp_dir_entry.get(),
            'silence_threshold': float(self.silence_thresh_slider.get()),
            'min_silence_len': float(self.min_silence_slider.get()),
            'safety_margin': float(self.margin_slider.get())
        })

        if not video_path:
            messagebox.showerror("Erro", "Selecione um arquivo de vídeo!")
            return
            
        if not self.settings['temp_dir']:
            self.settings['temp_dir'] = os.path.join(os.getcwd(), "temp")
            os.makedirs(self.settings['temp_dir'], exist_ok=True)
            self.temp_dir_entry.delete(0, tk.END)
            self.temp_dir_entry.insert(0, self.settings['temp_dir'])

        try:
            self.stop_event.clear()
            self.process_btn.config(state=tk.DISABLED)
            self.preview_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.progress['value'] = 0
            
            self.processing_thread = threading.Thread(
                target=self._run_processing, 
                args=(video_path, self.settings.copy()),
                daemon=True
            )
            self.processing_thread.start()
            
            self.root.after(100, self._update_progress)
            
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao iniciar processamento: {str(e)}")
            self._reset_interface()

    def _run_processing(self, video_path, settings):
        try:
            self.progress_queue.put(("log", "Iniciando processamento..."))
            self.progress_queue.put(("progress", 0))
            
            if settings['add_subtitles']:
                self.progress_queue.put(("log", "Carregando modelo Whisper..."))
                self.model = whisper.load_model(settings['whisper_model'])
                self.progress_queue.put(("log", f"Modelo {settings['whisper_model']} carregado com sucesso!"))
            
            processor = VideoProcessor(settings)
            
            video_dir = os.path.dirname(video_path)
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            
            if settings['add_subtitles']:
                output_dir = os.path.join(video_dir, "cortes_com_legendas")
            else:
                output_dir = os.path.join(video_dir, "cortes_sem_legendas")
            
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
                    temp_audio_path = os.path.join(settings['temp_dir'], f"temp_audio_{i + 1}.wav")
                    extract_audio_to_wav(final_clip_path, temp_audio_path)
                    
                    self.progress_queue.put(("log", "Transcrevendo áudio..."))
                    result = self.model.transcribe(temp_audio_path, language="pt", word_timestamps=True)
                    
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
                            "end": settings['clip_duration'],
                            "text": "[Conteúdo não verbal]"
                        }]
                    
                    transcription_text = " ".join([seg["text"] for seg in relevant_segments])
                    video_title = extract_keywords(transcription_text)
                    self.progress_queue.put(("log", f"Título sugerido: {video_title}"))

                    temp_clip_with_subtitles = os.path.join(settings['temp_dir'], f"clip_{i + 1}_legendas.mp4")
                    processor.add_subtitles_to_video(final_clip_path, temp_clip_with_subtitles, relevant_segments)

                    final_clip_with_subtitles = os.path.join(output_dir, f"{video_title}_clip_{i + 1}.mp4")
                    restore_audio_format(final_clip_path, temp_clip_with_subtitles, final_clip_with_subtitles)
                    
                    os.remove(temp_audio_path)
                    os.remove(temp_clip_with_subtitles)
                    os.remove(final_clip_path)  # Remove o clip sem legendas
                    self.last_clip_path = final_clip_with_subtitles
                    self.progress_queue.put(("log", f"Clip {i+1} (com legendas) salvo em: {final_clip_with_subtitles}"))
                else:
                    self.progress_queue.put(("log", f"Clip {i+1} (sem legendas) salvo em: {final_clip_path}"))

            if not self.stop_event.is_set():
                self.progress_queue.put(("complete", None))
            
        except Exception as e:
            self.progress_queue.put(("error", str(e)))

    def _update_progress(self):
        try:
            while True:
                msg_type, content = self.progress_queue.get_nowait()
                
                if msg_type == "log":
                    self.log_message(content)
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
        self.progress['value'] = 0
        self.process_btn.config(state=tk.NORMAL)
        self.preview_btn.config(state=tk.NORMAL if self.last_clip_path else tk.DISABLED)
        self.cancel_btn.config(state=tk.DISABLED)
        self.processing_thread = None

    def cancel_processing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            self.stop_event.set()
            self.log_message("Cancelando processamento...")
            self.cancel_btn.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoProcessorApp(root)
    root.mainloop()