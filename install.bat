@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ==========================================================================
REM  RhinoRAG 一键安装
REM  双击本文件即可。它会:
REM    1. 在本文件夹创建 Python 虚拟环境并安装依赖
REM    2. 从 GitHub Releases 下载预建的索引和模型 (rhino-rag-data.zip)
REM    3. 解压到本文件夹
REM  完成后请按 README.md 的"使用方法"把 MCP 配置粘贴到你的 AI 客户端。
REM ==========================================================================

set DATA_URL=https://github.com/KRLi3/RhinoRAG/releases/latest/download/rhino-rag-data.zip

cd /d "%~dp0"
echo.
echo ============================================================
echo   RhinoRAG 安装程序
echo ============================================================
echo.

REM --- 1. 检查 Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python。请先安装 Python 3.10+ 并勾选 "Add to PATH"。
    echo        下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- 2. 创建虚拟环境 ---
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 正在创建虚拟环境...
    python -m venv .venv
    if errorlevel 1 ( echo [错误] 创建虚拟环境失败。 & pause & exit /b 1 )
) else (
    echo [1/4] 虚拟环境已存在，跳过。
)

REM --- 3. 安装依赖 ---
echo [2/4] 正在安装依赖（首次约需几分钟，会下载 PyTorch 等）...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 ( echo [错误] 安装依赖失败。 & pause & exit /b 1 )

REM --- 4. 下载并解压数据包（索引 + 模型）---
if exist "db\rhinocommon\chroma.sqlite3" (
    echo [3/4] 索引已存在，跳过下载。
) else (
    echo [3/4] 正在下载索引和模型（约 150 MB）...
    ".venv\Scripts\python.exe" -c "import urllib.request,sys; urllib.request.urlretrieve('%DATA_URL%','rhino-rag-data.zip',lambda b,s,t:(sys.stdout.write('\r  %d MB'%(b*s/1048576)),sys.stdout.flush()))"
    if errorlevel 1 ( echo. & echo [错误] 下载失败，请检查网络或手动下载数据包。 & pause & exit /b 1 )
    echo.
    echo [4/4] 正在解压...
    ".venv\Scripts\python.exe" -c "import zipfile; zipfile.ZipFile('rhino-rag-data.zip').extractall('.')"
    if errorlevel 1 ( echo [错误] 解压失败。 & pause & exit /b 1 )
    del "rhino-rag-data.zip"
)

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo   下一步：把下面这段配置填进你的 AI 客户端（Claude 桌面 / VSCode）。
echo   详细步骤见 README.md 的"使用方法"。
echo.
echo   MCP 配置中的路径请使用：
echo     command: "%~dp0.venv\Scripts\python.exe"
echo     args:    "%~dp0mcp_server.py"
echo.
echo   （注意 JSON 里要把反斜杠 \ 写成 \\ 或正斜杠 /）
echo.
pause
endlocal
