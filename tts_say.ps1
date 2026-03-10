param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)

$text = ($Args -join " ").Trim()
if ([string]::IsNullOrWhiteSpace($text)) { exit 0 }

Add-Type -AssemblyName System.Speech
$tts = New-Object System.Speech.Synthesis.SpeechSynthesizer
$tts.Rate = 0
$tts.Speak($text)