"""Interface language. en is the source text. pt-BR translates what the user reads."""

from __future__ import annotations

import re

_language = "en"

_PT: dict[str, str] = {
    "thinking": "pensando",
    "Guide": "Guia",
    "Pick where to go": "Escolha para onde ir",
    "Pick the local model": "Escolha o modelo local",
    "llama-server in another terminal": "llama-server em outro terminal",
    "Ollama on this machine": "Ollama nesta máquina",
    "The menu is next.": "O menu vem em seguida.",
    "Chat": "Conversa",
    "Scripts": "Scripts",
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
    "Install 50 included scripts": "Instalar os 50 scripts inclusos",
    "Included scripts are ready in {directory}. The set has {count} scripts.": (
        "Os scripts inclusos estao prontos em {directory}. O conjunto tem {count} scripts."
    ),
    "DroidMCP setup scripts are ready: download droidmcp, configure droidmcp, droidmcp status.": (
        "Os scripts de preparacao do DroidMCP estao prontos: download droidmcp, configure droidmcp, droidmcp status."
    ),
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
    "Install a community script": "Instalar um script da comunidade",
    "Back": "Voltar",
    "Phone scripts": "Scripts do telefone",
    "Saved scripts": "Scripts salvos",
    "Create a script": "Criar um script",
    "Run a saved script": "Executar um script salvo",
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
    "Open another terminal and start llama-server there. Leave that terminal open.": (
        "Abra outro terminal e inicie o llama-server nele. Deixe esse terminal aberto."
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
    "The 50 included scripts are already installed.": "Os 50 scripts inclusos já estão instalados.",
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
    "On Termux run: pkg install dos2unix -y && dos2unix iniciar.sh && chmod +x iniciar.sh && ./iniciar.sh": (
        "No Termux rode: pkg install dos2unix -y && dos2unix iniciar.sh && chmod +x iniciar.sh && ./iniciar.sh"
    ),
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
    "The 50 included scripts are already in {directory}.": (
        "Os 50 scripts inclusos já estão em {directory}."
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
