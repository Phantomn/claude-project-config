$result=0

$reWriteModule = (Get-WebGlobalModule | Where-Object { $_.Name -eq "RewriteModule" } -ErrorAction SilentlyContinue).Name
if($reWriteModule -ne $null) {
    $url = "http://localhost"
    $httpRes = Invoke-WebRequest -Uri $url -Method head
    $httpBanner = $httpRes.Headers['Server']
    if($httpBanner -ne $null) {
        Write-Host "HTTP Server 배너가 노출되고 있습니다."
        $result += 1
    }

    $ftpRun = (Get-Service -Name ftpsvc).Status

    if($ftpRun -eq "Running") {
        $ftpServer = "localhost"
        $ftpClient = New-Object System.Net.Sockets.TcpClient
        $ftpClient.Connect($ftpServer, 21)
        $stream = $ftpClient.GetStream()
        $ftpRes = New-Object System.IO.StreamReader($stream)
        $ftpBanner = $ftpRes.ReadLine()
        if($ftpBanner -ne $null) {
            Write-Host "FTP 배너가 노출되고 있습니다."
            $result += 1
        }

        $ftpClient.Close()
    }
    
    $path = "C:\inetpub\AdminScripts"
    
    if(-not (Test-Path "$path\adsutil.vbs")) {
        Write-Host "adsutil.vbs 파일이 존재하지 않습니다."
        $result += 1
    }

    $cmd = "cscript $path\adsutil.vbs enum /p smtpsvc"
    $cmdResult = Invoke-Expression $cmd
    if($cmdResult -match "Version") {
        Write-Host "SMTP 배너가 노출되고 있습니다."
        $result += 1
    }
}
else {
    Write-Host "ReWriteModule이 설치되어 있지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"