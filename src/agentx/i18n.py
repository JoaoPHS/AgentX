"""Interface language. en is the source text. pt-BR translates what the user reads."""

from __future__ import annotations

import re

_language = "en"

_PT: dict[str, str] = {
    "thinking": "pensando",
    "Guide": "Guia",
    "Pick where to go": "Escolha para onde ir",
    "Pick the local model": "Escolha o modelo local",
    "llama-server, started by AgentX": "llama-server, iniciado pelo AgentX",
    "Speak a task": "Falar uma tarefa",
    "Listening. Speak the task.": "Ouvindo. Fale a tarefa.",
    "Heard: {text}": "Ouvi: {text}",
    "This script was blocked.": "Este script foi bloqueado.",
    "The script can delete files.": "O script pode apagar arquivos.",
    "The script path is not allowed.": "O caminho do script não é permitido.",
    "The script needs permission: {names}.": "O script precisa da permissão: {names}.",
    "That tool call is not valid.": "Essa chamada de ferramenta não é válida.",
    "DroidMCP timed out.": "O DroidMCP expirou.",
    "DroidMCP sent a mismatched reply.": "O DroidMCP devolveu uma resposta trocada.",
    "Remembered facts:": "Fatos lembrados:",
    "No facts are remembered yet.": "Nenhum fato foi lembrado ainda.",
    "Remembered {key}.": "Lembrei de {key}.",
    "Forgot {key}.": "Esqueci {key}.",
    "Chat history is saved.": "O histórico do chat está salvo.",
    "Chat history is not saved.": "O histórico do chat não está salvo.",
    "Chat history will be saved.": "O histórico do chat será salvo.",
    "Chat history will not be saved.": "O histórico do chat não será salvo.",
    "Chat history was cleared.": "O histórico do chat foi apagado.",
    "Use /chat on, /chat off, or /clear.": "Use /chat on, /chat off ou /clear.",
    "Restored {count} earlier turns.": "Restaurei {count} turnos anteriores.",
    "Saved chat: {state}": "Chat salvo: {state}",
    "Saved chat": "Chat salvo",
    "Save turns across launches": "Salvar turnos entre as sessões",
    "Do not save chat": "Não salvar o chat",
    "Keep earlier turns after AgentX exits": "Manter os turnos anteriores depois que o AgentX sair",
    "No memory named {key}.": "Nenhuma memória chamada {key}.",
    "Use /forget followed by the fact name.": "Use /forget seguido do nome do fato.",
    "Say what to remember, such as: remember that my server is home.": (
        "Diga o que lembrar, por exemplo: lembre que meu servidor é casa."
    ),
    "That memory is too long.": "Essa memória é longa demais.",
    "Secrets are not stored in memory.": "Segredos não são guardados na memória.",
    "Memory is full. Forget one fact first.": "A memória está cheia. Esqueça um fato primeiro.",
    "Safety check:": "Checagem de segurança:",
    "termux-speech-to-text is not on PATH. Install Termux:API and allow the microphone when Android asks.": (
        "termux-speech-to-text não está no PATH. Instale o Termux:API e permita o microfone quando o Android pedir."
    ),
    "Speech capture timed out. Install Termux:API and allow the microphone when Android asks.": (
        "A captura de voz expirou. Instale o Termux:API e permita o microfone quando o Android pedir."
    ),
    "No speech was recognized.": "Nenhuma fala foi reconhecida.",
    "Speech capture failed. Allow the microphone when Android asks.": (
        "A captura de voz falhou. Permita o microfone quando o Android pedir."
    ),
    "The Markdown reader did not return usable text.": (
        "O leitor de Markdown não devolveu texto útil."
    ),
    "The script reads or writes ~/.config/agentx or config.toml.": (
        "O script lê ou grava ~/.config/agentx ou config.toml."
    ),
    "The script walks outside its folder with ..": (
        "O script sai da pasta dele com .."
    ),
    "The script can start other processes.": "O script pode iniciar outros processos.",
    "The script runs a shell command.": "O script executa um comando de shell.",
    "The script reads the home directory.": "O script lê o diretório home.",
    "The script writes a file outside the usual script folder.": (
        "O script grava um arquivo fora da pasta usual de scripts."
    ),
    "The script reads environment variables.": "O script lê variáveis de ambiente.",
    "The script loads native code.": "O script carrega código nativo.",
    "BLOCK: The script reads or writes ~/.config/agentx or config.toml.": (
        "BLOQUEIO: O script lê ou grava ~/.config/agentx ou config.toml."
    ),
    "BLOCK: The script is not valid Python.": "BLOQUEIO: O script não é Python válido.",
    "BLOCK: The script loads native code.": "BLOQUEIO: O script carrega código nativo.",
    "BLOCK: The script runs a shell command.": "BLOQUEIO: O script executa um comando de shell.",
    "BLOCK: The script can delete files.": "BLOQUEIO: O script pode apagar arquivos.",
    "WARN: The script can start other processes.": "AVISO: O script pode iniciar outros processos.",
    "WARN: The script reads the home directory.": "AVISO: O script lê o diretório home.",
    "WARN: The script reads environment variables.": (
        "AVISO: O script lê variáveis de ambiente."
    ),
    "WARN: The script walks outside its folder with ..": (
        "AVISO: O script sai da pasta dele com .."
    ),
    "WARN: The script writes a file outside the usual script folder.": (
        "AVISO: O script grava um arquivo fora da pasta usual de scripts."
    ),
    "Chat  ·  /menu returns  ·  /voice speaks  ·  /exit quits": (
        "Conversa  ·  /menu volta  ·  /voice fala  ·  /exit sai"
    ),
    "Ollama on this machine": "Ollama nesta máquina",
    "The menu is next.": "O menu vem em seguida.",
    "Chat": "Conversa",
    "Scripts": "Scripts",
    "Hermes Bridge": "Ponte Hermes",
    "DroidNet Sentinel": "DroidNet Sentinel",
    "Saved reports": "Relatorios salvos",
    "Scan this network": "Varrer esta rede",
    "CVE notes": "Notas de CVE",
    "ARP cut, deauth, and exploit lookup stay off.": (
        "Corte ARP, deauth e busca de exploits ficam desligados."
    ),
    "DroidNet Sentinel is not configured. Set droidnet.path to a local clone.": (
        "O DroidNet Sentinel nao esta configurado. Defina droidnet.path para um clone local."
    ),
    "DroidNet Sentinel: {path}": "DroidNet Sentinel: {path}",
    "That DroidNet action stays off.": "Essa acao do DroidNet fica desligada.",
    "DroidNet scan was not started.": "A varredura do DroidNet nao foi iniciada.",
    "DroidNet Sentinel took too long.": "O DroidNet Sentinel demorou demais.",
    "DroidNet Sentinel failed.": "O DroidNet Sentinel falhou.",
    "DroidNet Sentinel finished.": "O DroidNet Sentinel terminou.",
    "Scan the current local network with DroidNet Sentinel? ARP cut, deauth, and exploit lookup stay off. [y/N] ": (
        "Varrer a rede local com o DroidNet Sentinel? Corte ARP, deauth e busca de exploits ficam desligados. [s/N] "
    ),
    "One shot, then the process exits": "Uma vez, e o processo encerra",
    "Worker": "Operário",
    "Orchestrator": "Orquestrador",
    "Task: ": "Tarefa: ",
    "Say what Hermes should do.": "Diga o que o Hermes deve fazer.",
    "Configuration": "Configuração",
    "Help guide": "Guia de ajuda",
    "Check config": "Verificar config",
    "Exit": "Sair",
    "↑↓ or number    enter select    q back": "↑↓ ou número    enter escolher    q voltar",
    "Number, enter, or q: ": "Número, enter ou q: ",
    "←→ pages    q back": "←→ páginas    q voltar",
    "In the menu, left and right move between these pages. q goes back.": (
        "No menu, esquerda e direita trocam estas páginas. q volta."
    ),
    "List installed scripts": "Listar scripts instalados",
    "Install 51 included scripts": "Instalar os 51 scripts inclusos",
    "Included scripts are ready in {directory}. The set has {count} scripts.": (
        "Os scripts inclusos estao prontos em {directory}. O conjunto tem {count} scripts."
    ),
    "DroidMCP setup scripts are ready: download droidmcp, configure droidmcp, droidmcp status.": (
        "Os scripts de preparacao do DroidMCP estao prontos: download droidmcp, configure droidmcp, droidmcp status."
    ),
    "Setup scripts: termux_setup, download_droidmcp, configure_droidmcp, check_droidmcp.": (
        "Scripts de preparacao: termux_setup, download_droidmcp, configure_droidmcp, check_droidmcp."
    ),
    "1. termux_setup": "1. termux_setup",
    "2. included_scripts": "2. included_scripts",
    "3. local_model": "3. local_model",
    "4. droidmcp": "4. droidmcp",
    "Installing dos2unix.": "Instalando o dos2unix.",
    "Installing dos2unix and Termux:API.": "Instalando o dos2unix e o Termux:API.",
    "Install the Termux:API app from F-Droid if Android asks for it.": (
        "Instale o app Termux:API pelo F-Droid se o Android pedir."
    ),
    "Updating the clone.": "Atualizando o clone.",
    "Fixing init.sh line endings.": "Corrigindo as quebras de linha do init.sh.",
    "Making init.sh executable.": "Tornando o init.sh executavel.",
    "Installing this AgentX folder.": "Instalando esta pasta do AgentX.",
    "Asking Termux for storage access.": "Pedindo acesso ao armazenamento do Termux.",
    "termux_setup finished.": "termux_setup concluido.",
    "The script finished.": "O script terminou.",
    "Set up DroidMCP sensors? Location, shell, SMS, contacts, and GitHub stay off. [y/N] ": (
        "Configurar os sensores do DroidMCP? Localizacao, shell, SMS, contatos e GitHub ficam desligados. [s/N] "
    ),
    "DroidMCP stays off.": "O DroidMCP continua desligado.",
    "The DroidMCP download did not match its checksum.": (
        "O download do DroidMCP nao bateu com a soma de verificacao."
    ),
    "The DroidMCP download failed.": "O download do DroidMCP falhou.",
    "The DroidMCP URL is not the pinned release.": "A URL do DroidMCP nao e a versao fixada.",
    "Open a terminal and confirm before DroidMCP is downloaded.": (
        "Abra um terminal e confirme antes de baixar o DroidMCP."
    ),
    "Continue with DroidMCP sensors? [y/N] ": "Continuar com os sensores do DroidMCP? [s/N] ",
    "DroidMCP file: ready": "Arquivo do DroidMCP: pronto",
    "DroidMCP file: missing": "Arquivo do DroidMCP: ausente",
    "Allowed tools: {tools}": "Ferramentas permitidas: {tools}",
    "Location, shell, SMS, contacts, and GitHub stay off.": (
        "Localizacao, shell, SMS, contatos e GitHub continuam desligados."
    ),
    "Status": "Status",
    "Download and set up": "Baixar e configurar",
    "Battery": "Bateria",
    "Wi-Fi": "Wi-Fi",
    "Brightness": "Brilho",
    "Volume": "Volume",
    "Sensor list": "Lista de sensores",
    "Sensors  ·  client {state}": "Sensores  ·  cliente {state}",
    "Download the sensors server?": "Baixar o servidor de sensores?",
    "Yes, download sensors": "Sim, baixar os sensores",
    "No, keep it off": "Nao, manter desligado",
    "DroidMCP sensors is ready.": "O DroidMCP de sensores esta pronto.",
    "DroidMCP is off. Choose Download and set up.": (
        "O DroidMCP esta desligado. Escolha Baixar e configurar."
    ),
    "Use Download and set up in this menu to turn the client on.": (
        "Use Baixar e configurar neste menu para ligar o cliente."
    ),
    "Install a community script": "Instalar um script da comunidade",
    "Back": "Voltar",
    "Phone scripts": "Scripts do telefone",
    "Saved scripts": "Scripts salvos",
    "Create a script": "Criar um script",
    "Run a saved script": "Executar um script salvo",
    "Pick a script to run": "Escolha um script para executar",
    "No script was chosen.": "Nenhum script foi escolhido.",
    "↑↓ enter run    ←→ pages    q back": "↑↓ enter executar    ←→ páginas    q voltar",
    "Script name: ": "Nome do script: ",
    "What the script does: ": "O que o script faz: ",
    "Task for the script: ": "Tarefa para o script: ",
    "Show current settings": "Mostrar ajustes atuais",
    "Model scope": "Escopo do modelo",
    "Language": "Idioma",
    "Interface language": "Idioma da interface",
    "Save a provider key": "Salvar uma chave de API",
    "Saved settings": "Ajustes salvos",
    "Local": "Local",
    "All roles on the remote key": "Todos os papéis na chave remota",
    "Analysis on the remote key": "Análise na chave remota",
    "Main agent on the remote key": "Agente principal na chave remota",
    "Where the key is used": "Onde a chave é usada",
    "English": "Inglês",
    "Brazilian Portuguese": "Português do Brasil",
    "Provider (openrouter, anthropic, openai): ": "Provedor (openrouter, anthropic, openai): ",
    "Key: ": "Chave: ",
    "Script name or gist URL: ": "Nome do script ou URL do gist: ",
    "enter returns": "enter volta",
    "Chat  ·  /menu returns  ·  /exit quits": "Conversa  ·  /menu volta  ·  /exit sai",
    "Install this script? [y/N] ": "Instalar este script? [s/N] ",
    "Use llama-server? No saves Ollama in the config. [y/N] ": (
        "Usar o llama-server? Não grava o Ollama na config. [s/N] "
    ),
    "AgentX starts llama-server in the background when a task needs it.": (
        "O AgentX inicia o llama-server em segundo plano quando uma tarefa precisa dele."
    ),
    "It stops that process when AgentX exits, or after it sits idle.": (
        "Ele encerra esse processo quando o AgentX sai, ou depois que fica ocioso."
    ),
    "Keep using AgentX in this terminal.": "Continue usando o AgentX neste terminal.",
    "Ollama is the local engine now.": "O Ollama passa a ser o motor local.",
    "Config saved: local.provider = {provider}.": "Config gravada: local.provider = {provider}.",
    "Open another terminal and start Ollama there. Leave that terminal open.": (
        "Abra outro terminal e inicie o Ollama nele. Deixe esse terminal aberto."
    ),
    "The model name is {model}. Pull it in that terminal if Ollama does not have it yet.": (
        "O nome do modelo é {model}. Baixe nesse terminal se o Ollama ainda não tiver o modelo."
    ),
    "Install Qwen2.5-1.5B-Instruct Q4_K_M? [y/N] ": (
        "Instalar o Qwen2.5-1.5B-Instruct Q4_K_M? [s/N] "
    ),
    "Name a Hugging Face model or GGUF to search for: ": (
        "Diga um modelo ou GGUF do Hugging Face para buscar: "
    ),
    "Skipped the local model.": "Modelo local ignorado.",
    "The model file is not in the 986M to 1.1G range, so it was not registered.": (
        "O arquivo não está entre 986M e 1,1G, então não foi registrado."
    ),
    "llama-server answered a short request, then it was stopped.": (
        "O llama-server respondeu um pedido curto e depois foi encerrado."
    ),
    "Ollama is not on PATH. llama-server can still use the GGUF file.": (
        "O Ollama não está no PATH. O llama-server ainda pode usar o arquivo GGUF."
    ),
    "The model URL must be an HTTPS Hugging Face GGUF.": (
        "A URL do modelo precisa ser um GGUF HTTPS do Hugging Face."
    ),
    "The model download failed.": "O download do modelo falhou.",
    "Use agentx doctor.": "Use agentx doctor.",
    "Use agentx mcp tools.": "Use agentx mcp tools.",
    "DroidMCP listed no tools.": "O DroidMCP não listou ferramentas.",
    "Command names stay off.": "Nomes de comando continuam desligados.",
    "Set mcp.enabled and mcp.tools in the config to allow a call.": (
        "Defina mcp.enabled e mcp.tools na config para permitir uma chamada."
    ),
    "Client: on": "Cliente: ligado",
    "Client: off": "Cliente: desligado",
    "Use script list, script new NAME, script run NAME, script add FILE, script install NAME, or script examples.": (
        "Use script list, script new NOME, script run NOME, script add ARQUIVO, script install NOME ou script examples."
    ),
    "Script not installed.": "Script não instalado.",
    "A file name is only used with a gist.": "Um nome de arquivo só é usado com um gist.",
    "The 51 included scripts are already installed.": "Os 51 scripts inclusos já estão instalados.",
    "Installed {count} scripts in {directory}.": "Instalados {count} scripts em {directory}.",
    "Installed scripts: none.": "Scripts instalados: nenhum.",
    "Installed scripts:": "Scripts instalados:",
    "The request failed.": "O pedido falhou.",
    "Use /engineer followed by the task.": "Use /engineer seguido da tarefa.",
    "Session: local.": "Sessão: local.",
    "Unknown language. Use en, pt, or pt-BR.": "Idioma desconhecido. Use en, pt ou pt-BR.",
    "Could not write the config file.": "Não foi possível gravar o arquivo de config.",
    "Warning: the config file should have mode 600.": (
        "Aviso: o arquivo de config deveria ter o modo 600."
    ),
    "The config file is not valid TOML.": "O arquivo de config não é TOML válido.",
    "Unknown key scope. Use local, all, orchestrator, or main.": (
        "Escopo de chave desconhecido. Use local, all, orchestrator ou main."
    ),
    "Command tools are off.": "Ferramentas de comando estão desligadas.",
    "The config value max_tokens must be a positive integer.": (
        "O valor max_tokens da config precisa ser um inteiro positivo."
    ),
    "Config file: FAIL": "Arquivo de config: FALHA",
    "The config file is missing. Run agentx init.": (
        "O arquivo de config não existe. Rode agentx init."
    ),
    "Config file: OK": "Arquivo de config: OK",
    "TOML: FAIL": "TOML: FALHA",
    "TOML: OK": "TOML: OK",
    "remote_scope: FAIL (unknown)": "remote_scope: FALHA (desconhecido)",
    "remote_scope: OK": "remote_scope: OK",
    "remote_provider: FAIL (unknown)": "remote_provider: FALHA (desconhecido)",
    "remote_provider: OK": "remote_provider: OK",
    "local.provider: FAIL (unknown)": "local.provider: FALHA (desconhecido)",
    "local.provider: OK": "local.provider: OK",
    "local.model: OK": "local.model: OK",
    "local.model: FAIL (missing)": "local.model: FALHA (ausente)",
    "local.base_url: OK": "local.base_url: OK",
    "local.base_url: FAIL (not loopback)": "local.base_url: FALHA (não é loopback)",
    "local.model_path: FAIL (missing)": "local.model_path: FALHA (ausente)",
    "local.model_path: FAIL (path is not a file)": (
        "local.model_path: FALHA (o caminho não é um arquivo)"
    ),
    "local.model_path: OK": "local.model_path: OK",
    "config permissions: WARN": "permissões da config: AVISO",
    "config permissions: OK": "permissões da config: OK",
    "mcp: OK (off)": "mcp: OK (desligado)",
    "mcp: WARN (binary not on PATH)": "mcp: AVISO (binário fora do PATH)",
    "mcp: OK": "mcp: OK",
    "mcp tools: FAIL (command tools are off)": (
        "ferramentas mcp: FALHA (ferramentas de comando estão desligadas)"
    ),
    "routing: FAIL (malformed)": "routing: FALHA (malformado)",
    "local: FAIL (malformed)": "local: FALHA (malformado)",
    "mcp: FAIL (malformed)": "mcp: FALHA (malformado)",
    "The local model path is missing from the config.": (
        "O caminho do modelo local não está na config."
    ),
    "The local model file does not exist.": "O arquivo do modelo local não existe.",
    "llama-server is not on PATH.": "llama-server não está no PATH.",
    "The Ollama base URL must use 127.0.0.1 or localhost.": (
        "A URL do Ollama precisa usar 127.0.0.1 ou localhost."
    ),
    "The Ollama model name is missing from the config.": (
        "O nome do modelo Ollama não está na config."
    ),
    "Could not start llama-server.": "Não foi possível iniciar o llama-server.",
    "llama-server did not become ready in time.": (
        "O llama-server não ficou pronto a tempo."
    ),
    "Could not read free memory. The local model will not start.": (
        "Não foi possível ler a memória livre. O modelo local não vai iniciar."
    ),
    "The phone is too hot. Generation is paused until it cools down.": (
        "O telefone está quente demais. A geração fica pausada até esfriar."
    ),
    "The device is warm. The screenshot was not taken.": (
        "O aparelho está quente. A captura de tela não foi feita."
    ),
    "DroidMCP stopped.": "DroidMCP parado.",
    "The request timed out.": "O pedido expirou.",
    "The local model is not available to run the task.": (
        "O modelo local não está disponível para executar a tarefa."
    ),
    "The request is ambiguous, so it was not sent.": (
        "O pedido é ambíguo, então não foi enviado."
    ),
    "Summarizing the page.": "Resumindo a página.",
    "DroidMCP is not available.": "O DroidMCP não está disponível.",
    "The MCP client is off.": "O cliente MCP está desligado.",
    "The worker instruction is missing.": "Falta a instrução do worker.",
    "The MCP arguments are invalid.": "Os argumentos do MCP são inválidos.",
    "Calling delegate_to_worker.": "Chamando delegate_to_worker.",
    "That tool is not allowed.": "Essa ferramenta não é permitida.",
    "That tool is not available.": "Essa ferramenta não está disponível.",
    "The MCP root is missing from the config.": "A raiz MCP não está na config.",
    "DroidMCP did not list its tools.": "O DroidMCP não listou as ferramentas.",
    "DroidMCP returned an empty result.": "O DroidMCP devolveu um resultado vazio.",
    "DroidMCP could not run that tool.": "O DroidMCP não conseguiu executar essa ferramenta.",
    "DroidMCP closed the connection.": "O DroidMCP fechou a conexão.",
    "DroidMCP sent a malformed header.": "O DroidMCP enviou um cabeçalho malformado.",
    "DroidMCP sent malformed JSON.": "O DroidMCP enviou JSON malformado.",
    "Local scope does not use a remote key.": "O escopo local não usa chave remota.",
    "The remote model failed.": "O modelo remoto falhou.",
    "The local model failed.": "O modelo local falhou.",
    "The key was rejected.": "A chave foi recusada.",
    "The remote API did not accept that model id.": (
        "A API remota não aceitou esse id de modelo."
    ),
    "The reply reached the token limit.": "A resposta atingiu o limite de tokens.",
    "The URL must be http or https.": "A URL precisa ser http ou https.",
    "The URL cannot include a username or password.": (
        "A URL não pode incluir usuário ou senha."
    ),
    "The URL is blocked.": "A URL está bloqueada.",
    "Could not resolve the URL.": "Não foi possível resolver a URL.",
    "The page returned an empty redirect.": "A página devolveu um redirecionamento vazio.",
    "Too many redirects.": "Redirecionamentos demais.",
    "Only HTML pages can be extracted.": "Só páginas HTML podem ser extraídas.",
    "The page had no text to extract.": "A página não tinha texto para extrair.",
    "\n\nThe text was cut because it was long.": "\n\nO texto foi cortado porque era longo.",
    "This page looks script-rendered, and the browser extra is not installed.": (
        "Esta página parece renderizada por script, e o extra de navegador não está instalado."
    ),
    "The browser extra could not render the page.": (
        "O extra de navegador não conseguiu renderizar a página."
    ),
    "This page looks script-rendered, and rendering did not return usable text.": (
        "Esta página parece renderizada por script, e a renderização não devolveu texto útil."
    ),
    "Could not read the script.": "Não foi possível ler o script.",
    "Use a short script name: letters, digits, and underscores.": (
        "Use um nome curto de script: letras, dígitos e sublinhado."
    ),
    "The script is not valid Python.": "O script não é Python válido.",
    "Add a docstring that says what the script does.": (
        "Adicione uma docstring que diga o que o script faz."
    ),
    "Add a keywords or patterns line to the docstring, such as: keywords: toast, popup": (
        "Adicione uma linha keywords ou patterns na docstring, por exemplo: keywords: toast, popup"
    ),
    "The script name is not allowed.": "O nome do script não é permitido.",
    "The script timed out.": "O script expirou.",
    "No matching script. Pick one by name: run script NAME.": (
        "Nenhum script combinou. Escolha um pelo nome: run script NOME."
    ),
    "Type /scripts to see the full list.": "Digite /scripts para ver a lista completa.",
    "The script could not be started.": "O script não pôde ser iniciado.",
    "The script failed.": "O script falhou.",
    "The script finished with no output.": "O script terminou sem saída.",
    "Installing does not mean this script is safe.": (
        "Instalar não significa que este script é seguro."
    ),
    "The gist response was not valid JSON.": "A resposta do gist não era JSON válido.",
    "The gist has no files.": "O gist não tem arquivos.",
    "The gist file has no content.": "O arquivo do gist não tem conteúdo.",
    "That gist id is not valid.": "Esse id de gist não é válido.",
    "The gist has no Python script.": "O gist não tem um script Python.",
    "The script index is not valid JSON.": "O índice de scripts não é JSON válido.",
    "The script index is malformed.": "O índice de scripts está malformado.",
    "Script installs use https only.": "A instalação de scripts usa só https.",
    "The script download failed.": "O download do script falhou.",
    "The download is too large.": "O download é grande demais.",
    "That host is not allowed for script installs.": (
        "Esse host não é permitido para instalar scripts."
    ),
    "not set": "não definido",
    "none": "nenhum",
    "on": "ligado",
    "off": "desligado",
    "Binary: {binary}": "Binário: {binary}",
    "Tools: {tools}": "Ferramentas: {tools}",
    "Session: {provider}, scope {scope}.": "Sessão: {provider}, escopo {scope}.",
    "Session: {provider}, model {model}.": "Sessão: {provider}, modelo {model}.",
    "Local provider: ollama, model {model}.": "Provedor local: ollama, modelo {model}.",
    "Language: {language}.": "Idioma: {language}.",
    "Saved the {provider} key.": "Chave {provider} salva.",
    "Use /model local, /model all, /model orchestrator, or /model main. The scope applies to the remote key in the config. Use /model ollama MODEL to set the local Ollama model.": (
        "Use /model local, /model all, /model orchestrator ou /model main. "
        "O escopo vale para a chave remota da config. "
        "Use /model ollama MODELO para definir o modelo local do Ollama."
    ),
    "Use /key openrouter, /key anthropic, or /key openai, followed by the key.": (
        "Use /key openrouter, /key anthropic ou /key openai, seguido da chave."
    ),
    "Use agentx key openrouter, agentx key anthropic, or agentx key openai, followed by the key.": (
        "Use agentx key openrouter, agentx key anthropic ou agentx key openai, seguido da chave."
    ),
    "Config already exists at {path}.": "A config já existe em {path}.",
    "Termux starter written to {path}.": "Inicializador do Termux gravado em {path}.",
    "Config written to {path}": "Config gravada em {path}",
    "Saved {path}. Edit it, then run: agentx script run {name}": (
        "Salvo em {path}. Edite o arquivo e rode: agentx script run {name}"
    ),
    "No scripts are saved yet. Create one with: agentx script new NAME.": (
        "Ainda não há scripts salvos. Crie um com: agentx script new NOME."
    ),
    "Saved scripts:": "Scripts salvos:",
    "More than one script matches: {names}. Run one with: run script NAME.": (
        "Mais de um script combina: {names}. Rode um com: run script NOME."
    ),
    "Saving the script.": "Salvando o script.",
    "Use agentx script new NAME to save a script.": "Use agentx script new NOME para salvar um script.",
    "Installed {names}": "Instalados: {names}",
    "Installed {names} in {directory}": "Instalados: {names} em {directory}",
    "The 51 included scripts are already in {directory}.": (
        "Os 51 scripts inclusos já estão em {directory}."
    ),
    "Script written to {path}": "Script gravado em {path}",
    "No scripts in {directory}. Create one with: agentx script new NAME.": (
        "Nenhum script em {directory}. Crie um com: agentx script new NOME."
    ),
    "Scripts in {directory}:": "Scripts em {directory}:",
    "Language: {language}": "Idioma: {language}",
    "Local: {provider}, {shown}": "Local: {provider}, {shown}",
    "Remote: {provider}, scope {scope}": "Remoto: {provider}, escopo {scope}",
    "MCP: {state}, tools {tools}": "MCP: {state}, ferramentas {tools}",
    "Scripts: {directory}": "Scripts: {directory}",
    "{name}: {size} bytes": "{name}: {size} bytes",
    "{name}: allowed": "{name}: permitido",
    "{name}: off": "{name}: desligado",
}

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^The config section (\w+) is malformed\.$"), "A seção {0} da config está malformada."),
    (re.compile(r"^The config value (\w+) must be text\.$"), "O valor {0} da config precisa ser texto."),
    (
        re.compile(r"^The config value (\w+) must be true or false\.$"),
        "O valor {0} da config precisa ser true ou false.",
    ),
    (
        re.compile(r"^The config value (\w+) must be a list of text\.$"),
        "O valor {0} da config precisa ser uma lista de texto.",
    ),
    (
        re.compile(r"^The config value (\w+) must be an integer\.$"),
        "O valor {0} da config precisa ser um número inteiro.",
    ),
    (
        re.compile(r"^The config file is not valid TOML \(line (\d+), column (\d+)\)\.$"),
        "O arquivo de config não é TOML válido (linha {0}, coluna {1}).",
    ),
    (
        re.compile(r"^The config file is not valid TOML \(line (\d+)\)\.$"),
        "O arquivo de config não é TOML válido (linha {0}).",
    ),
    (
        re.compile(r"^Unknown remote provider\. Use (.+)\.$"),
        "Provedor remoto desconhecido. Use {0}.",
    ),
    (
        re.compile(r"^Unknown local provider\. Use (.+)\.$"),
        "Provedor local desconhecido. Use {0}.",
    ),
    (
        re.compile(r"^Free memory is below (\d+) MB\. The local model will not start\.$"),
        "A memória livre está abaixo de {0} MB. O modelo local não vai iniciar.",
    ),
    (re.compile(r"^Ollama is not running on (.+)\.$"), "O Ollama não está em execução em {0}."),
    (
        re.compile(r"^The Ollama model (.+) is not installed\. Pull it with: ollama pull (.+)$"),
        "O modelo Ollama {0} não está instalado. Baixe com: ollama pull {1}",
    ),
    (
        re.compile(r"^\[WARN\] CPU at (\d+) C: pausing until it cools\.$"),
        "[AVISO] CPU a {0} C: pausando temporariamente para resfriamento.",
    ),
    (
        re.compile(r"^\[WARN\] CPU at (\d+) C: using one thread until it cools\.$"),
        "[AVISO] CPU a {0} C: usando uma thread até esfriar.",
    ),
    (
        re.compile(r"^DroidMCP could not run that tool \((-?\d+)\)\.$"),
        "O DroidMCP não conseguiu rodar essa ferramenta ({0}).",
    ),
    (re.compile(r"^Unknown script: (.+)\.$"), "Script desconhecido: {0}."),
    (
        re.compile(r"^Unknown script (.+)\. The index has: (.+)\.$"),
        "Script desconhecido {0}. O índice tem: {1}.",
    ),
    (re.compile(r"^Script (.+) already exists\.$"), "O script {0} já existe."),
    (re.compile(r"^Running (.+)\.$"), "Executando {0}."),
    (re.compile(r"^Calling (.+)\.$"), "Chamando {0}."),
    (re.compile(r"^Missing the (.+) key\.$"), "Falta a chave {0}."),
    (
        re.compile(r"^Missing the (.+) model id in the config\.$"),
        "Falta o id do modelo {0} na config.",
    ),
    (
        re.compile(r"^The remote API did not accept the model id (.+)\.$"),
        "A API remota não aceitou o id de modelo {0}.",
    ),
    (re.compile(r"^The gist has no file named (.+)\.$"), "O gist não tem um arquivo chamado {0}."),
    (
        re.compile(r"^The gist has more than one Python script\. Name the file: (.+)\.$"),
        "O gist tem mais de um script Python. Diga o arquivo: {0}.",
    ),
    (re.compile(r"^The page returned status (\d+)\.$"), "A página devolveu o status {0}."),
    (re.compile(r"^TOML: FAIL \(line (\d+), column (\d+)\)$"), "TOML: FALHA (linha {0}, coluna {1})"),
    (re.compile(r"^TOML: FAIL \(line (\d+)\)$"), "TOML: FALHA (linha {0})"),
    (re.compile(r"^(.+) API key: OK$"), "chave de API {0}: OK"),
    (re.compile(r"^(.+) API key: FAIL \(missing\)$"), "chave de API {0}: FALHA (ausente)"),
    (re.compile(r"^Source: (.+)$"), "Origem: {0}"),
    (re.compile(r"^The script sends HTTP to (.+)\.$"), "O script envia HTTP para {0}."),
    (re.compile(r"^The script imports (.+) and can send network requests\.$"), (
        "O script importa {0} e pode enviar pedidos de rede."
    )),
    (re.compile(r"^The script calls (.+)\.$"), "O script chama {0}."),
    (re.compile(r"^BLOCK: (.+)$"), "BLOQUEIO: {0}"),
    (re.compile(r"^WARN: (.+)$"), "AVISO: {0}"),
)


def current_language() -> str:
    return _language


def set_language(language: str) -> None:
    global _language
    _language = "pt-BR" if language == "pt-BR" else "en"


def t(message: str) -> str:
    if _language != "pt-BR" or not message:
        return message
    found = _PT.get(message)
    if found is not None:
        return found
    if "\n" in message:
        return "\n".join(t(line) for line in message.split("\n"))
    for pattern, template in _PATTERNS:
        match = pattern.fullmatch(message)
        if match:
            return template.format(*match.groups())
    return message


def tr(template: str, **kwargs: object) -> str:
    return t(template).format(**kwargs)
