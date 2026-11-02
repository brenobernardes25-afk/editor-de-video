# Monta o pacote de venda a partir da pasta "conteudo".
# Uso (no PowerShell, dentro da pasta pacote-venda):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\montar-pacote.ps1
# Gera: editor-de-video-pacote.zip (o arquivo que o comprador baixa)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$conteudo = Join-Path $raiz 'conteudo'
$skill = Join-Path $conteudo 'editor-de-video'
$tmp = Join-Path $raiz '_montagem'
$saida = Join-Path $raiz 'editor-de-video-pacote.zip'

Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem

function Novo-Zip($destino, $itens) {
  # $itens: lista de @{ Arquivo = caminho no disco; Nome = caminho dentro do zip (com /) }
  if (Test-Path $destino) { Remove-Item $destino -Force }
  $zip = [System.IO.Compression.ZipFile]::Open($destino, 'Create')
  try {
    foreach ($i in $itens) {
      [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $i.Arquivo, $i.Nome, 'Optimal')
    }
  } finally { $zip.Dispose() }
}

if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory $tmp | Out-Null

# 1) a skill (editor-de-video.zip), com caminhos editor-de-video/...
$itensSkill = Get-ChildItem $skill -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' } | ForEach-Object {
  @{ Arquivo = $_.FullName; Nome = 'editor-de-video/' + $_.FullName.Substring($skill.Length + 1).Replace('\', '/') }
}
$zipSkill = Join-Path $tmp 'editor-de-video.zip'
Novo-Zip $zipSkill $itensSkill
Write-Host ("editor-de-video.zip: {0} arquivos" -f @($itensSkill).Count)

# 2) o pacote final
$itens = @(
  @{ Arquivo = $zipSkill; Nome = 'editor-de-video.zip' },
  @{ Arquivo = (Join-Path $conteudo 'LEIA-ME.txt'); Nome = 'LEIA-ME.txt' },
  @{ Arquivo = (Join-Path $conteudo 'INSTRUCOES_GPT.txt'); Nome = 'INSTRUCOES_GPT.txt' }
)
$modelo = Join-Path $conteudo 'whisper-small-pt.npz'
if (Test-Path $modelo) {
  $itens += @{ Arquivo = $modelo; Nome = 'whisper-small-pt.npz' }
  Write-Host ("modelo incluido: {0:N0} MB" -f ((Get-Item $modelo).Length / 1MB))
} else {
  Write-Warning 'whisper-small-pt.npz nao esta em conteudo\ - o pacote saiu SEM o modelo (veja PARA-O-VENDEDOR.txt).'
}
Novo-Zip $saida $itens
Remove-Item $tmp -Recurse -Force
Write-Host ("PRONTO: {0} ({1:N1} MB)" -f $saida, ((Get-Item $saida).Length / 1MB))
