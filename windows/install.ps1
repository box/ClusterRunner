# variables
$url = "https://cloud.box.com/shared/static/u91zg1fmmlxo2reqo8mwi3hjv7kaeazz.zip"
if ($env:TEMP -eq $null) {
  $env:TEMP = Join-Path $env:SystemDrive 'temp'
}
$crTempDir = Join-Path $env:TEMP "clusterrunner"
$tempDir = Join-Path $crTempDir "crInstall"
if (![System.IO.Directory]::Exists($tempDir)) {[System.IO.Directory]::CreateDirectory($tempDir)}
$file = Join-Path $tempDir "clusterrunner.zip"

function Download-File {
param (
  [string]$url,
  [string]$file
 )
  Write-Host "Downloading $url to $file"
  $downloader = new-object System.Net.WebClient
  $downloader.Proxy.Credentials=[System.Net.CredentialCache]::DefaultNetworkCredentials;
  $downloader.DownloadFile($url, $file)
}

# download the package
Download-File $url $file

# download 7zip
Write-Host "Download 7Zip commandline tool"
$7zaExe = Join-Path $tempDir '7za.exe'

Download-File 'https://chocolatey.org/7za.exe' "$7zaExe"

# unzip the package
$targetDir = Join-Path $env:userprofile ".clusterrunner"
if (![System.IO.Directory]::Exists($targetDir)) {[System.IO.Directory]::CreateDirectory($targetDir)}
Write-Host "Extracting $file to .clusterrunner"
Start-Process "$7zaExe" -ArgumentList "x -o`"$targetDir`" -y `"$file`"" -Wait -NoNewWindow
$defaultConf = $targetDir, "dist", "conf", "default_clusterrunner.conf" -join "\"
$targetConf = Join-path $targetDir "clusterrunner.conf"
Copy-Item $defaultConf $targetConf
