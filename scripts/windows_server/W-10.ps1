function Get-HttpStatusCode {
    param (
        [Parameter(Mandatory=$true)]
        [string]$Uri
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -ErrorAction Stop
        return $response.StatusCode
    } catch {
        return 0
    }
}

$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState

if($server -eq "Installed") {
    $statusCode = Get-HttpStatusCode -Uri "http://localhost"
    
    if($statusCode -ne 200) {
        $iis = Get-Service -Name "W3SVC" -ErrorAction SilentlyContinue

        if($iis) {
            Write-Host "IIS is Running"
            $result += 1
        }
    }
}

Write-Host "점검 결과: $result"