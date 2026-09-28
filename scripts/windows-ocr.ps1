param([Parameter(Mandatory=$true)][string]$InputPath, [string]$Pages = '')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$asAction = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
} | Select-Object -First 1
function Await($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}
function Recognize($Stream) {
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($Stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $transform = New-Object Windows.Graphics.Imaging.BitmapTransform
    $ratio = [Math]::Min(1, [Windows.Media.Ocr.OcrEngine]::MaxImageDimension / [double][Math]::Max($decoder.PixelWidth, $decoder.PixelHeight))
    $transform.ScaledWidth = [uint32][Math]::Max(1, [Math]::Floor($decoder.PixelWidth * $ratio))
    $transform.ScaledHeight = [uint32][Math]::Max(1, [Math]::Floor($decoder.PixelHeight * $ratio))
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync(
        [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
        [Windows.Graphics.Imaging.BitmapAlphaMode]::Ignore, $transform,
        [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation,
        [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        ($result.Lines | ForEach-Object { $_.Text }) -join "`n"
    } finally { $bitmap.Dispose() }
}
try {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) {
        $language = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Select-Object -First 1
        if ($language) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language) }
    }
    if ($null -eq $engine) { throw 'Windows has no OCR language installed. Add a language in Windows Settings > Time & language, then retry the import.' }
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($InputPath)) ([Windows.Storage.StorageFile])
    if ([IO.Path]::GetExtension($InputPath).ToLowerInvariant() -eq '.pdf') {
        $pdf = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
        foreach ($number in ($Pages -split ',')) {
            $page = $pdf.GetPage([uint32]([int]$number - 1))
            $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
            try {
                $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
                $scale = [Math]::Min(3, [Windows.Media.Ocr.OcrEngine]::MaxImageDimension / [Math]::Max($page.Size.Width, $page.Size.Height))
                $options.DestinationWidth = [uint32][Math]::Max(1, [Math]::Floor($page.Size.Width * $scale))
                $options.DestinationHeight = [uint32][Math]::Max(1, [Math]::Floor($page.Size.Height * $scale))
                $renderTask = $asAction.Invoke($null, @($page.RenderToStreamAsync($stream, $options)))
                $renderTask.GetAwaiter().GetResult()
                $stream.Seek(0)
                @{page=[int]$number; text=(Recognize $stream); language=$engine.RecognizerLanguage.LanguageTag} | ConvertTo-Json -Compress
            } finally { $stream.Dispose(); $page.Dispose() }
        }
    } else {
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        try { @{page=1; text=(Recognize $stream); language=$engine.RecognizerLanguage.LanguageTag} | ConvertTo-Json -Compress }
        finally { $stream.Dispose() }
    }
} catch {
    @{error=$_.Exception.Message} | ConvertTo-Json -Compress
    exit 1
}
