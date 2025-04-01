import os
import subprocess
import whisper
from moviepy import VideoFileClip, CompositeVideoClip, TextClip, VideoClip
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
import json
from pathlib import Path
import matplotlib.font_manager as fm
from PIL import ImageFont, ImageDraw

# Configurações constantes
CONFIG_DIR = os.path.join(Path.home(), ".video_processor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

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

class FontManager:
    def __init__(self):
        self.system_fonts = self._load_windows_fonts()
        self._test_fallback_fonts()
    
    def _test_fallback_fonts(self):
        """Testa fontes de fallback para garantir que pelo menos uma funciona"""
        self.fallback_fonts = [
            'Liberation-Sans', 'DejaVu-Sans', 'FreeSans', 
            'Verdana', 'Arial', 'Arial-Unicode-MS'
        ]
        
        for font in self.fallback_fonts:
            if self.is_font_available(font):
                self.default_font = font
                return
        self.default_font = None
        
    def get_default_font(self):
        """Retorna uma fonte padrão que sabemos que funciona"""
        return self.default_font or 'Liberation-Sans'
    
    def _load_windows_fonts(self):
        """Carrega apenas as fontes do Windows de forma direta"""
        try:
            # Lista direta das fontes mais comuns no Windows
            common_windows_fonts = [
                'Arial', 'Calibri', 'Cambria', 'Candara', 'Comic Sans MS', 
                'Consolas', 'Constantia', 'Corbel', 'Courier New', 
                'Georgia', 'Impact', 'Lucida Console', 'Lucida Sans Unicode',
                'Microsoft Sans Serif', 'Palatino Linotype', 'Segoe UI', 
                'Tahoma', 'Times New Roman', 'Trebuchet MS', 'Verdana'
            ]
            
            # Filtra apenas as fontes que realmente existem no sistema
            available_fonts = []
            for font in common_windows_fonts:
                try:
                    font_path = fm.findfont(font, fallback_to_default=False)
                    if os.path.exists(font_path):
                        available_fonts.append(font)
                except:
                    continue
            
            return sorted(available_fonts)
            
        except:
            # Fallback básico se algo der errado
            return ['Arial', 'Courier New', 'Times New Roman', 'Verdana']
    
    def get_available_fonts(self):
        """Retorna apenas as fontes do Windows disponíveis"""
        return self.system_fonts
    
    def get_font_path(self, font_name):
        """Retorna o caminho da fonte no sistema com fallback robusto"""
        try:
            # Tentativa principal
            font_path = fm.findfont(font_name, fallback_to_default=False)
            if os.path.exists(font_path):
                return font_path
            
            # Fallback 1: Tentar encontrar a fonte sem exceções
            font_path = fm.findfont(font_name.replace(' ', '-'), fallback_to_default=False)
            if os.path.exists(font_path):
                return font_path
                
            # Fallback 2: Tentar variações comuns
            variations = {
                'Arial': ['arial', 'arial.ttf', 'Arial.ttf'],
                'Courier New': ['cour', 'cour.ttf'],
                'Times New Roman': ['times', 'times.ttf'],
                'Verdana': ['verdana', 'verdana.ttf']
            }
            
            if font_name in variations:
                for variation in variations[font_name]:
                    try:
                        path = fm.findfont(variation, fallback_to_default=False)
                        if os.path.exists(path):
                            return path
                    except:
                        continue
            
            # Fallback final: Arial ou fonte padrão do sistema
            return fm.findfont('Arial')
            
        except Exception as e:
            print(f"Erro ao encontrar fonte {font_name}: {e}")
            return fm.findfont('Arial')
    
    def is_font_available(self, font_name):
        """Verifica se uma fonte pode ser carregada"""
        try:
            font_path = self.get_font_path(font_name)
            # Testa se a fonte pode ser carregada pelo PIL
            test_font = ImageFont.truetype(font_path, 10)
            return test_font is not None
        except:
            return False
class VideoProcessor:
    def __init__(self, config, temp_manager, font_manager):
        self.config = config
        self.temp_manager = temp_manager
        self.font_manager = font_manager  # Adicionar referência ao FontManager
        
    def check_fonts(self):
        """Verifica fontes disponíveis e exibe no log"""
        test_fonts = ['Arial', 'Liberation-Sans', 'DejaVu-Sans', 'Verdana']
        available = []
        for font in test_fonts:
            if self.font_manager.is_font_available(font):
                available.append(font)
        
        print(f"Fontes disponíveis: {', '.join(available) if available else 'Nenhuma fonte encontrada'}")
        print(f"Usando fonte padrão: {self.font_manager.get_default_font()}")
    
    def _create_text_clip(self, text, font_name, font_size, video_width, color='white', stroke_color='black', stroke_width=1):
        """Cria um TextClip com tratamento robusto de erros de fonte"""
        try:
            font_size = int(font_size)
            stroke_width = int(stroke_width) if stroke_width else 0
            font_path = self.font_manager.get_font_path(font_name)
            
            if not font_path or not os.path.exists(font_path):
                raise ValueError(f"Fonte {font_name} não encontrada")
            
            # Configurações do stroke (contorno)
            stroke_settings = {}
            if stroke_color.lower() != 'none':
                stroke_settings = {
                    'stroke_color': stroke_color,
                    'stroke_width': stroke_width
                }
            
            # Garantir que video_width seja inteiro
            width = int(video_width * 0.9)
            
            return TextClip(
                text=text,
                font=font_path,
                font_size=font_size,  # CORREÇÃO: usar font_size em vez de fontsize
                size=(width, None),
                color=color,
                method='caption',
                **stroke_settings
            )
        except Exception as e:
            print(f"Erro ao criar TextClip ({str(e)}), usando configurações mínimas")
            # Fallback seguro com valores inteiros explícitos
            try:
                return TextClip(
                    text=text,
                    font_size=24,  # Tamanho fixo para fallback
                    size=(int(video_width * 0.9), None),
                    color=color,
                    font='Liberation-Sans'  # Fonte alternativa mais confiável
                )
            except Exception as fallback_error:
                print(f"Erro no fallback: {fallback_error}")
                # Último recurso - sem fonte especificada
                return TextClip(
                    text=text,
                    font_size=24,
                    size=(int(video_width * 0.9), None),
                    color=color
                )
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
                
                if end - start < 2000:  # Pelo menos 2 segundos
                    continue
                    
                moments.append(start / 1000)  # Converter para segundos
            
            if not moments:
                return self._fallback_segments(video_path)
            return moments
            
        except Exception as e:
            print(f"Erro ao analisar áudio: {e}")
            return self._fallback_segments(video_path)

    def _create_animated_text(self, text, duration, font_name, font_size, color, stroke_color, stroke_width, video_width):
        """Cria um texto com animação de digitação com destaque na palavra atual"""
        try:
            font_path = self.font_manager.get_font_path(font_name)
            if not font_path or not os.path.exists(font_path):
                font_path = self.font_manager.get_font_path(self.font_manager.get_default_font())
            
            # Configurações
            highlight_color = '#FFFF00'  # Amarelo para destacar
            base_color = color
            stroke_settings = {
                'stroke_color': stroke_color,
                'stroke_width': int(stroke_width) if stroke_width else 1
            } if stroke_color and stroke_color.lower() != 'none' else {}
            
            # Divide o texto em palavras mantendo espaços e pontuação
            words = re.findall(r'\w+|\s+|[^\w\s]', text)
            
            # Cria clips base
            base_clip_normal = TextClip(
                "", font=font_path, font_size=int(font_size),
                color=base_color, size=(int(video_width * 0.9), None),
                method='caption', **stroke_settings
            )
            
            base_clip_highlight = TextClip(
                "", font=font_path, font_size=int(font_size),
                color=highlight_color, size=(int(video_width * 0.9), None),
                method='caption', **stroke_settings
            )
            
            # Calcula tempo por palavra
            total_words = len([w for w in words if w.strip()])
            words_per_second = max(1, total_words/duration)
            
            def make_frame(t):
                current_word_idx = min(len(words), int(t * words_per_second))
                if current_word_idx < len(words):
                    # Suaviza a transição entre palavras
                    progress = (t * words_per_second) - current_word_idx
                    if progress > 0.8:  # Começa a mostrar a próxima palavra nos últimos 20% do tempo
                        current_word_idx += 1
                displayed_words = words[:current_word_idx]
                
                # Separa as palavras já exibidas da palavra atual (se houver)
                normal_text = ''.join(displayed_words[:-1]) if current_word_idx > 0 else ""
                current_word = displayed_words[-1] if current_word_idx > 0 else ""
                
                # Cria os clips separados
                if normal_text:
                    normal_clip = base_clip_normal.with_text(normal_text)
                    frame = normal_clip.get_frame(t)
                else:
                    frame = base_clip_normal.with_text("").get_frame(t)
                
                if current_word:
                    # Posiciona o clip da palavra destacada
                    if normal_text:
                        # Calcula a posição X da palavra atual
                        temp_clip = base_clip_normal.with_text(normal_text)
                        try:
                            normal_width = temp_clip.size[0]
                        except:
                            normal_width = len(normal_text) * font_size * 0.6  # Fallback aproximado
                        current_word_clip = base_clip_highlight.with_text(current_word)
                        highlight_frame = current_word_clip.get_frame(t)
                        
                        # Desenha a palavra destacada na posição correta
                        x_offset = normal_width
                        frame[x_offset:x_offset+current_word_clip.size[0], :] = highlight_frame
                    else:
                        # Primeira palavra
                        current_word_clip = base_clip_highlight.with_text(current_word)
                        frame = current_word_clip.get_frame(t)
                
                # Adiciona cursor piscante (opcional)
                if int(t * 2) % 2 == 0 and current_word_idx < len(words):
                    cursor = base_clip_highlight.with_text("|").get_frame(t)
                    cursor_x = frame.shape[1] - 20  # Posição do cursor
                    frame[cursor_x:cursor_x+10, :] = cursor[:, :10]
                
                return frame
                
            animated_text = VideoClip(make_frame, duration=duration)
            return animated_text.crossfadein(0.3).crossfadeout(0.3)
            
        except Exception as e:
            print(f"Erro na animação avançada: {e}")
            return self._create_text_clip(text, font_name, font_size, video_width, color, stroke_color, stroke_width)
    def _fallback_segments(self, video_path):
        """Método alternativo caso a análise de áudio falhe"""
        try:
            with VideoFileClip(video_path) as clip:
                duration = clip.duration
                clip_duration = self.config.get('clip_duration', 45)
                return [i for i in range(0, int(duration), clip_duration)]
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
        """Adiciona legendas ao vídeo com tratamento robusto de fontes"""
        try:
            with VideoFileClip(video_path) as video:
                subtitle_clips = []
                for segment in segments:
                    try:
                        # Configurações com fallback
                        font = subtitle_config.get('font', 'Arial')
                        font_size = int(subtitle_config.get('font_size', 24))
                        color = subtitle_config.get('font_color', 'white')
                        stroke_color = subtitle_config.get('stroke_color', 'black')
                        stroke_width = int(subtitle_config.get('stroke_width', 1))
                        use_animation = subtitle_config.get('animation', False)
                        
                        if use_animation:
                            text_clip = self._create_animated_text(
                                text=segment["text"],
                                duration=segment["end"] - segment["start"],
                                font_name=font,
                                font_size=font_size,
                                color=color,
                                stroke_color=stroke_color,
                                stroke_width=stroke_width,
                                video_width=video.w
                            )
                        else:
                            text_clip = self._create_text_clip(
                                text=segment["text"],
                                font_name=font,
                                font_size=font_size,
                                video_width=video.w,
                                color=color,
                                stroke_color=stroke_color,
                                stroke_width=stroke_width
                            )
                        
                        position = self._get_subtitle_position(
                            subtitle_config.get('position', 'bottom'),
                            video.h
                        )
                        
                        subtitle_clip = text_clip.with_position(position).with_start(segment["start"])
                        if not use_animation:
                            subtitle_clip = subtitle_clip.with_duration(segment["end"] - segment["start"])
                        
                        subtitle_clips.append(subtitle_clip)
                    except Exception as e:
                        print(f"Erro ao criar legenda para segmento: {str(e)}")
                        continue

                if subtitle_clips:
                    final_video = CompositeVideoClip([video] + subtitle_clips)
                    final_video.write_videofile(
                        output_path,
                        codec="libx264",
                        audio_codec="aac",
                        fps=video.fps,
                        threads=4,
                        preset='medium',  # Melhor qualidade que 'fast'
                        bitrate="8000k",  # Ajuste conforme necessário
                        ffmpeg_params=['-crf', '18']  # Qualidade visual (18-28 é bom)
                    )
                else:
                    raise ValueError("Nenhuma legenda pôde ser criada")
        except Exception as e:
            print(f"Erro ao adicionar legendas: {e}")
            raise
    def _get_subtitle_position(self, position, video_height):
        """Retorna a posição das legendas baseado na configuração"""
        if position == 'top':
            return ('center', 50)
        elif position == 'middle':
            return ('center', 'center')
        else:  # bottom
            return ('center', video_height - 100)

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
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.config = {}  # Configurações padrão
        self.temp_manager = TempFileManager()
        self.font_manager = FontManager()
        
        # Garante que o diretório de configuração existe
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        # Cria arquivo de configuração padrão se não existir
        if not os.path.exists(CONFIG_FILE):
            self._create_default_config()
        
        self._setup_ui()
        self._initialize_variables()
        self._load_auto_settings()  # Carrega as configurações existentes
        
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_default_config(self):
        """Cria um arquivo de configuração padrão"""
        default_config = {
            'whisper_model': 'medium',
            'clip_duration': 45,
            'use_gpu': False,
            'silence_threshold': -40,
            'min_silence_len': 1.0,
            'safety_margin': 0.5,
            'add_subtitles': True,
            'font': 'Arial',
            'font_size': 24,
            'font_color': 'white',
            'stroke_color': 'black',
            'position': 'bottom',
            'last_video_path': '',
            'animation': True,
            'highlight_color': '#FFFF00',
            'animation_style': 'Digitação com Destaque'
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f, indent=4)
    def _initialize_variables(self):
        """Inicializa variáveis e gerenciadores"""
        self.model = None
        self.progress_queue = queue.Queue()
        self.processing_thread = None
        self.stop_event = threading.Event()
        self.last_clip_path = None

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

        ttk.Label(settings_frame, text="Modelo Whisper:").grid(row=0, column=0, sticky=tk.W)
        self.model_combo = ttk.Combobox(settings_frame, values=['tiny', 'base', 'small', 'medium', 'large'], state="readonly")
        self.model_combo.set('medium')
        self.model_combo.grid(row=0, column=1, padx=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Usar GPU:").grid(row=0, column=2, sticky=tk.W)
        self.use_gpu_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, variable=self.use_gpu_var).grid(row=0, column=3, padx=5, sticky=tk.W)

        ttk.Label(settings_frame, text="Duração do Clip (s):").grid(row=0, column=4, sticky=tk.W)
        self.duration_entry = ttk.Entry(settings_frame, width=8)
        self.duration_entry.insert(0, "45")
        self.duration_entry.grid(row=0, column=5, padx=5, sticky=tk.W)
        self.duration_entry.config(validate="key", 
            validatecommand=(self.duration_entry.register(self._validate_number), '%P'))

        ttk.Label(settings_frame, text="Adicionar legendas:").grid(row=1, column=0, sticky=tk.W)
        self.add_subtitles_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, variable=self.add_subtitles_var).grid(row=1, column=1, padx=5, sticky=tk.W)

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
        self.log_text = tk.Text(main_frame, height=10, width=70)
        self.log_text.grid(row=6, column=0, columnspan=3, sticky=tk.EW, pady=5)

        # Botões de controle
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=10)
        
        self.process_btn = ttk.Button(btn_frame, text="Processar Vídeo", command=self._process_video)
        self.process_btn.pack(side=tk.LEFT, padx=5)

        self.preview_btn = ttk.Button(btn_frame, text="Pré-visualizar Último Clip", command=self._preview_last_clip, state=tk.DISABLED)
        self.preview_btn.pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(btn_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        ttk.Button(btn_frame, text="Salvar Config", command=self._save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Carregar Config", command=self._load_settings).pack(side=tk.LEFT, padx=5)

        self.cancel_btn = ttk.Button(btn_frame, text="Cancelar", 
                                    command=self._cancel_processing, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        main_frame.columnconfigure(1, weight=1)
        advanced_frame.columnconfigure(1, weight=1)
        self.subtitle_frame.columnconfigure(1, weight=1)

    def _create_slider(self, parent, label_text, row, from_, to, initial):
        """Cria um slider com label e valor exibido"""
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W)
        slider = ttk.Scale(parent, from_=from_, to=to, value=initial)
        slider.grid(row=row, column=1, padx=5, sticky=tk.EW)
        value_label = ttk.Label(parent, text=str(initial))
        value_label.grid(row=row, column=2)
        slider.config(command=lambda v: value_label.config(text=f"{float(v):.1f}"))
        
        # Adicione atribuição dinâmica baseada no label_text
        if "Limiar" in label_text:
            self.silence_threshold_slider = slider
        elif "Duração Mínima" in label_text:
            self.min_silence_len_slider = slider
        elif "Margem Segurança" in label_text:
            self.safety_margin_slider = slider
        
        return slider

    def _create_subtitle_settings(self, parent):
        """Configurações completas de legendas"""
        frame = ttk.LabelFrame(parent, text="Configurações de Legendas", padding=10)
        
        # Adicione controles para a animação
        ttk.Label(frame, text="Estilo de Animação:").grid(row=7, column=0, sticky=tk.W)
        self.animation_style = ttk.Combobox(frame, values=[
            'Digitação Simples', 
            'Digitação com Destaque', 
            'Digitação com Cursor'
        ], state="readonly")
        self.animation_style.set('Digitação com Destaque')
        self.animation_style.grid(row=7, column=1 , padx=5, sticky=tk.W)
        # Cor do destaque
        ttk.Label(frame, text="Cor de Destaque:").grid(row=6, column=0, sticky=tk.W)
        self.highlight_color = ttk.Combobox(frame, values=[
            '#FFFF00', '#FF0000', '#00FF00', '#0000FF', '#FFFFFF'
        ], state="readonly")
        self.highlight_color.set('#FFFF00')
        self.highlight_color.grid(row=6, column=1, padx=5, sticky=tk.W)
        # Adicione este novo controle no final:
        ttk.Label(frame, text="Animação:").grid(row=5, column=0, sticky=tk.W)
        self.animation_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Ativar animação", variable=self.animation_var).grid(row=5, column=1, sticky=tk.W)
        # Configurações de fonte
        ttk.Label(frame, text="Fonte:").grid(row=0, column=0, sticky=tk.W)
        self.font_combo = ttk.Combobox(frame, state="readonly")
        self.font_combo['values'] = self.font_manager.get_available_fonts()
        self.font_combo.set('Arial' if 'Arial' in self.font_combo['values'] else self.font_combo['values'][0])
        self.font_combo.grid(row=0, column=1, padx=5, sticky=tk.EW)
        
        # Tamanho da fonte
        ttk.Label(frame, text="Tamanho:").grid(row=1, column=0, sticky=tk.W)
        self.font_size = ttk.Spinbox(frame, from_=8, to=72, width=5)
        self.font_size.set(24)
        self.font_size.grid(row=1, column=1, padx=5, sticky=tk.W)
        
        # Cor do texto
        ttk.Label(frame, text="Cor do texto:").grid(row=2, column=0, sticky=tk.W)
        self.font_color = ttk.Combobox(frame, values=['white', 'yellow', 'black', 'red', 'green', 'blue'], state="readonly")
        self.font_color.set('white')
        self.font_color.grid(row=2, column=1, padx=5, sticky=tk.W)
        
        # Cor do contorno
        ttk.Label(frame, text="Cor do contorno:").grid(row=3, column=0, sticky=tk.W)
        self.stroke_color = ttk.Combobox(frame, values=['black', 'white', 'none', 'red', 'green', 'blue'], state="readonly")
        self.stroke_color.set('black')
        self.stroke_color.grid(row=3, column=1, padx=5, sticky=tk.W)
        
        # Posição
        ttk.Label(frame, text="Posição:").grid(row=4, column=0, sticky=tk.W)
        self.sub_position = ttk.Combobox(frame, values=['top', 'middle', 'bottom'], state="readonly")
        self.sub_position.set('bottom')
        self.sub_position.grid(row=4, column=1, padx=5, sticky=tk.W)
        
        return frame

    def _load_available_fonts(self):
        """Carrega fontes disponíveis de forma confiável"""
        try:
            all_fonts = self.font_manager.get_available_fonts()
            
            # Verificar disponibilidade das fontes
            available_fonts = []
            for font in all_fonts:
                if self.font_manager.is_font_available(font):
                    available_fonts.append(font)
            
            # Ordenar colocando as comuns primeiro
            common_fonts = ['Arial', 'Courier New', 'Times New Roman', 'Verdana', 'Helvetica']
            font_list = sorted(
                available_fonts, 
                key=lambda x: (x not in common_fonts, x)
            )
            
            self.font_combo['values'] = font_list
            
            # Definir fonte padrão segura
            safe_fonts = [f for f in common_fonts if f in font_list]
            if safe_fonts:
                self.font_combo.set(safe_fonts[0])
            else:
                self.font_combo.set(font_list[0] if font_list else 'Arial')
                
        except Exception as e:
            print(f"Erro ao carregar fontes: {e}")
            self.font_combo['values'] = ['Arial']
            self.font_combo.set('Arial')

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
            self._save_auto_settings()

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
            'use_gpu': self.use_gpu_var.get(),
            'temp_dir': os.path.join(os.getcwd(), "temp"),
            'silence_threshold': float(self.silence_threshold_slider.get()),
            'min_silence_len': float(self.min_silence_len_slider.get()),
            'safety_margin': float(self.safety_margin_slider.get()),
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
            
            # Verificar fontes disponíveis
            processor = VideoProcessor(settings, self.temp_manager, self.font_manager)
            processor.check_fonts()
            
            if settings['add_subtitles']:
                selected_font = self.font_combo.get()
                if not self.font_manager.is_font_available(selected_font):
                    self.progress_queue.put(("log", f"Aviso: Fonte '{selected_font}' não encontrada, usando Arial como fallback"))
                    selected_font = 'Arial'
                    
                subtitle_config = {
                    'font': self.font_combo.get(),
                    'font_size': int(self.font_size.get()),
                    'font_color': self.font_color.get(),
                    'stroke_color': None if self.stroke_color.get() == 'none' else self.stroke_color.get(),
                    'stroke_width': 1.5,
                    'position': self.sub_position.get(),
                    'animation': self.animation_var.get()  # Nova configuração
                }
                self.progress_queue.put(("log", "Carregando modelo Whisper..."))
                device = "cuda" if settings.get('use_gpu', False) else "cpu"
                self.model = whisper.load_model(settings['whisper_model'], device=device)
                self.progress_queue.put(("log", f"Modelo {settings['whisper_model']} carregado com sucesso no dispositivo {device.upper()}!"))
            
            processor = VideoProcessor(settings, self.temp_manager, self.font_manager)
            
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
                self._save_auto_settings()
            
        except Exception as e:
            self.progress_queue.put(("error", str(e)))

    def _process_transcription_result(self, result, clip_duration):
        """Processa o resultado da transcrição com tempos precisos"""
        relevant_segments = []
        
        for segment in result["segments"]:
            text = segment["text"].strip()
            start = segment["start"]
            end = segment["end"]
            
            if len(text) < 3 or text in ["...", "[música]", "[risos]"]:
                continue
                
            # Divide textos muito longos em múltiplos segmentos
            max_duration = 5.0  # segundos por segmento
            if (end - start) > max_duration:
                words = text.split()
                word_duration = (end - start) / len(words)
                chunks = []
                current_chunk = []
                current_duration = 0
                
                for word in words:
                    current_chunk.append(word)
                    current_duration += word_duration
                    
                    if current_duration >= max_duration or word[-1] in ".!?":
                        chunk_text = " ".join(current_chunk)
                        chunk_end = start + current_duration
                        chunks.append({
                            "text": chunk_text,
                            "start": start,
                            "end": chunk_end
                        })
                        start = chunk_end
                        current_chunk = []
                        current_duration = 0
                
                if current_chunk:
                    chunks.append({
                        "text": " ".join(current_chunk),
                        "start": start,
                        "end": end
                    })
                    
                relevant_segments.extend(chunks)
            else:
                relevant_segments.append({
                    "text": text,
                    "start": start,
                    "end": end
                })
        
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

    def _get_current_settings(self):
        """Retorna um dicionário com todas as configurações atuais"""
        return {
            'whisper_model': self.model_combo.get(),
            'clip_duration': int(self.duration_entry.get()),
            'use_gpu': self.use_gpu_var.get(),
            'silence_threshold': float(self.silence_threshold_slider.get()),
            'min_silence_len': float(self.min_silence_len_slider.get()),
            'safety_margin': float(self.safety_margin_slider.get()),
            'add_subtitles': self.add_subtitles_var.get(),
            'font': self.font_combo.get(),
            'font_size': int(self.font_size.get()),
            'font_color': self.font_color.get(),
            'stroke_color': self.stroke_color.get(),
            'position': self.sub_position.get(),
            'last_video_path': self.video_path_entry.get(),
            'animation': self.animation_var.get(),
            'highlight_color': self.highlight_color.get(),
            'animation_style': self.animation_style.get()
        }

    def _save_auto_settings(self):
        """Salva as configurações automaticamente no arquivo padrão"""
        try:
            settings = self._get_current_settings()
            with open(CONFIG_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações automáticas: {e}")

    def _load_auto_settings(self):
        """Carrega as configurações automaticamente do arquivo padrão"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    settings = json.load(f)
                
                # Configurações básicas
                self.model_combo.set(settings.get('whisper_model', 'medium'))
                self.duration_entry.delete(0, tk.END)
                self.duration_entry.insert(0, str(settings.get('clip_duration', 45)))
                self.use_gpu_var.set(settings.get('use_gpu', False))
                
                # Sliders
                self.silence_threshold_slider.set(settings.get('silence_threshold', -40))
                self.min_silence_len_slider.set(settings.get('min_silence_len', 1.0))
                self.safety_margin_slider.set(settings.get('safety_margin', 0.5))
                
                # Legendas
                self.add_subtitles_var.set(settings.get('add_subtitles', True))
                self.font_combo.set(settings.get('font', 'Arial'))
                self.font_size.delete(0, tk.END)
                self.font_size.insert(0, str(settings.get('font_size', 24)))
                self.font_color.set(settings.get('font_color', 'white'))
                self.stroke_color.set(settings.get('stroke_color', 'black'))
                self.sub_position.set(settings.get('position', 'bottom'))
                
                # Animação
                self.animation_var.set(settings.get('animation', True))
                self.highlight_color.set(settings.get('highlight_color', '#FFFF00'))
                self.animation_style.set(settings.get('animation_style', 'Digitação com Destaque'))
                
                # Último vídeo
                last_video = settings.get('last_video_path', '')
                if last_video and os.path.exists(last_video):
                    self.video_path_entry.delete(0, tk.END)
                    self.video_path_entry.insert(0, last_video)
                
                self._log_message("Configurações carregadas automaticamente")
        except Exception as e:
            print(f"Erro ao carregar configurações automáticas: {e}")
            # Se houver erro, cria um novo arquivo padrão
            self._create_default_config()

    def _save_settings(self):
        """Salva as configurações atuais no arquivo de configuração padrão"""
        try:
            settings = self._get_current_settings()
            with open(CONFIG_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
            self._log_message("Configurações salvas com sucesso!")
            messagebox.showinfo("Sucesso", "Configurações salvas automaticamente!")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar configurações: {str(e)}")

    def _load_settings(self):
        """Carrega configurações de um arquivo JSON"""
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")],
            title="Carregar Configurações",
            initialdir=CONFIG_DIR
        )
        
        if filepath:
            try:
                with open(filepath, 'r') as f:
                    settings = json.load(f)
                
                self.model_combo.set(settings.get('whisper_model', 'medium'))
                self.duration_entry.delete(0, tk.END)
                self.duration_entry.insert(0, str(settings.get('clip_duration', 45)))
                self.use_gpu_var.set(settings.get('use_gpu', False))
                self.silence_threshold_slider.set(settings.get('silence_threshold', -40))
                self.min_silence_len_slider.set(settings.get('min_silence_len', 1.0))
                self.safety_margin_slider.set(settings.get('safety_margin', 0.5))
                self.add_subtitles_var.set(settings.get('add_subtitles', True))
                self.font_combo.set(settings.get('font', 'Arial'))
                self.font_size.delete(0, tk.END)
                self.font_size.insert(0, str(settings.get('font_size', 62)))
                self.font_color.set(settings.get('font_color', 'yellow'))
                self.stroke_color.set(settings.get('stroke_color', 'black'))
                self.sub_position.set(settings.get('position', 'bottom'))
                
                self._log_message(f"Configurações carregadas de: {filepath}")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao carregar configurações: {str(e)}")

    def _on_close(self):
        """Executado quando a janela está fechando"""
        try:
            self._save_settings()  # Usa o mesmo método de salvar
            self.temp_manager.cleanup()
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao fechar aplicativo: {str(e)}")
            self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoProcessorApp(root)
    root.mainloop()
