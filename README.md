README - Video Processor / Processador de Vídeo
English Version
📹 Video Processor with Automatic Subtitles
A Python application that automatically processes videos by:

Detecting interesting segments based on audio analysis

Creating short clips from these segments

Optionally adding automatic subtitles using OpenAI's Whisper

Allowing preview of generated clips

✨ Features
Smart segmentation: Finds interesting moments by analyzing audio patterns

Automatic subtitles: Generates and embeds subtitles using Whisper AI

Configurable settings: Adjustable parameters for silence detection and clip duration

Preview functionality: Watch generated clips before finalizing

Multilingual: Supports Portuguese and English content

Fast processing: Option to skip subtitles for quicker processing

⚙️ Requirements
Python 3.8+

FFmpeg (must be in system PATH)

The following Python packages:

Copy
matplotlib
whisper
moviepy
pydub
tkinter
🛠 Installation
Clone the repository:

bash
Copy
git clone https://github.com/monokatarina/cut_caption.git
cd video-processor
Install dependencies:

bash
Copy
pip install -r requirements.txt
Make sure FFmpeg is installed on your system.

🚀 Usage
Run the application:

bash
Copy
python video_processor.py
In the GUI:

Select your input video file

Choose processing settings

Check "Add subtitles" if you want automatic subtitles

Click "Process Video"

Generated clips will be saved in:

cortes_com_legendas (with subtitles)

cortes_sem_legendas (without subtitles)

⚡ Performance Tips
For faster processing without subtitles, uncheck "Add subtitles"

Smaller Whisper models (tiny, base) are faster but less accurate

Adjust silence threshold to better match your video's audio characteristics



!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!



Versão em Português
📹 Processador de Vídeo com Legendas Automáticas
Aplicação em Python que processa vídeos automaticamente:

Detecta segmentos interessantes baseado em análise de áudio

Cria clipes curtos desses segmentos

Opcionalmente adiciona legendas automáticas usando Whisper da OpenAI

Permite pré-visualização dos clipes gerados

✨ Funcionalidades
Segmentação inteligente: Encontra momentos interessantes analisando padrões de áudio

Legendas automáticas: Gera e insere legendas usando Whisper AI

Configurações ajustáveis: Parâmetros personalizáveis para detecção de silêncio e duração de clipes

Pré-visualização: Visualize os clipes gerados antes de finalizar

Multilíngue: Suporta conteúdo em Português e Inglês

Processamento rápido: Opção para pular legendas para processamento mais rápido

⚙️ Requisitos
Python 3.8+

FFmpeg (deve estar no PATH do sistema)

Os seguintes pacotes Python:

Copy
matplotlib
whisper
moviepy
pydub
tkinter
� Instalação
Clone o repositório:

bash
Copy
git clone https://github.com/monokatarina/cut_caption.git
cd processador-video
Instale as dependências:

bash
Copy
pip install -r requirements.txt
Certifique-se que o FFmpeg está instalado no seu sistema.

🚀 Como Usar
Execute a aplicação:

bash
Copy
python video_processor.py
Na interface gráfica:

Selecione seu arquivo de vídeo

Escolha as configurações de processamento

Marque "Adicionar legendas" se desejar legendas automáticas

Clique em "Processar Vídeo"

Os clipes gerados serão salvos em:

cortes_com_legendas (com legendas)

cortes_sem_legendas (sem legendas)

⚡ Dicas de Performance
Para processamento mais rápido sem legendas, desmarque "Adicionar legendas"

Modelos menores do Whisper (tiny, base) são mais rápidos mas menos precisos

Ajuste o limiar de silêncio para melhorar a detecção de acordo com o áudio do seu vídeo
