@echo off
:: Instalador Automático para CutCaption
echo #########################################
echo #   INSTALADOR CUTCAPTION - MONOKATARINA #
echo #########################################
echo.
echo Este instalador vai configurar tudo o que você precisa!

:: Verificar se o Python está instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python não encontrado! Baixando Python...
    start "" "https://www.python.org/downloads/"
    echo Por favor, instale o Python e execute este instalador novamente
    pause
    exit
)

:: Instalar dependências
echo Instalando as dependências do Python...
pip install --upgrade pip
pip install whisper moviepy pydub ffmpeg-python

:: Baixar FFmpeg
echo Baixando FFmpeg...
curl -L "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -o ffmpeg.zip
if exist ffmpeg.zip (
    tar -xf ffmpeg.zip
    move "ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe" .
    rd /s /q "ffmpeg-master-latest-win64-gpl"
    del ffmpeg.zip
) else (
    echo Não foi possível baixar o FFmpeg automaticamente
    echo Baixe manualmente em: https://ffmpeg.org/download.html
)

:: Criar atalho
echo Criando atalho...
echo @echo off > CutCaption.bat
echo python "%~dp0cut_caption.py" %%* >> CutCaption.bat

echo.
echo #########################################
echo # Instalação concluída com sucesso!
echo # Execute o programa usando:
echo # 1. Clique duas vezes em CutCaption.bat
echo # OU
echo # 2. Execute: python video_processor.py
echo #########################################
pause
