// Voice Navigator local speech host. Uses only Windows/.NET components.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Speech.Recognition;
using System.Speech.Synthesis;
using System.Text;
using System.Security;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;

internal static class VoiceHost {
    [DllImport("winmm.dll")]
    private static extern uint waveInGetNumDevs();
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    private static readonly object OutputLock = new object();
    private static SpeechRecognitionEngine Engine;
    private static SpeechSynthesizer Synth;
    private static volatile bool Speaking;
    private static DateTime QuietUntil = DateTime.MinValue;
    private static readonly ManualResetEvent Finished = new ManualResetEvent(false);
    private static void Emit(object value) {
        lock (OutputLock) {
            try { Console.WriteLine(Json.Serialize(value)); Console.Out.Flush(); }
            catch (IOException) { }
        }
    }
    private static string Text(Dictionary<string, object> obj, string key, string fallback) {
        object value;
        return obj.TryGetValue(key, out value) && value != null ?
            Convert.ToString(value, CultureInfo.InvariantCulture) : fallback;
    }
    private static string[] Strings(Dictionary<string, object> obj, string key) {
        object value; var result = new List<string>();
        if (obj.TryGetValue(key, out value) && value is IEnumerable && !(value is string))
            foreach (object item in (IEnumerable)value)
                if (item != null) result.Add(Convert.ToString(item));
        return result.ToArray();
    }
    private static Dictionary<string, object> Read(string line) {
        return Json.Deserialize<Dictionary<string, object>>(line);
    }
    private static int Number(Dictionary<string, object> obj, string key, int fallback) {
        object value;
        return obj.TryGetValue(key, out value) && value != null ?
            Convert.ToInt32(value, CultureInfo.InvariantCulture) : fallback;
    }
    private static void Speak(string text, Dictionary<string, object> settings) {
        if (String.IsNullOrWhiteSpace(text)) return;
        Speaking = true;
        try {
            if (Synth == null) Synth = new SpeechSynthesizer();
            string voice = Text(settings, "tts_voice", "");
            if (!String.IsNullOrWhiteSpace(voice)) Synth.SelectVoice(voice);
            Synth.Rate = Math.Max(-10, Math.Min(10, Number(settings, "tts_rate", 0)));
            Synth.Volume = Math.Max(0, Math.Min(100, Number(settings, "tts_volume", 100)));
            Synth.SetOutputToDefaultAudioDevice();
            string pitch = Text(settings, "tts_pitch", "normal").ToLowerInvariant();
            if (pitch != "low" && pitch != "high") pitch = "medium";
            string language = Synth.Voice == null ? "en-US" : Synth.Voice.Culture.Name;
            string safeText = SecurityElement.Escape(text);
            Synth.SpeakSsml("<speak version=\"1.0\" xmlns=\"http://www.w3.org/2001/10/synthesis\" xml:lang=\"" +
                SecurityElement.Escape(language) + "\"><prosody pitch=\"" + pitch + "\">" + safeText +
                "</prosody></speak>");
        } finally {
            QuietUntil = DateTime.UtcNow.AddMilliseconds(800);
            Speaking = false;
        }
    }
    [STAThread]
    private static int Main() {
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
        try {
            string first = Console.ReadLine();
            if (first == null) return 0;
            Dictionary<string, object> settings = Read(first);
            string mode = Text(settings, "mode", "listen");
            if (mode == "tts_preview") {
                Speak(Text(settings, "text", "Voice Navigator test."), settings);
                Emit(new { type = "tts_preview" });
                return 0;
            }
            var recognizers = SpeechRecognitionEngine.InstalledRecognizers();
            var descriptions = new List<object>();
            foreach (RecognizerInfo item in recognizers)
                descriptions.Add(new { id = item.Id, name = item.Name, culture = item.Culture.Name });
            if (mode == "probe") {
                var voices = new List<object>();
                using (var speaker = new SpeechSynthesizer())
                    foreach (InstalledVoice installed in speaker.GetInstalledVoices())
                        if (installed.Enabled)
                            voices.Add(new { name = installed.VoiceInfo.Name, id = installed.VoiceInfo.Id,
                                culture = installed.VoiceInfo.Culture.Name,
                                gender = installed.VoiceInfo.Gender.ToString() });
                Emit(new { type = "probe", recognizers = descriptions,
                    voices = voices, available = recognizers.Count > 0, x64 = Environment.Is64BitProcess });
                return recognizers.Count > 0 || voices.Count > 0 ? 0 : 2;
            }
            if (recognizers.Count == 0)
                throw new InvalidOperationException(
                    "No Windows desktop speech recognizer is available to this process. " +
                    "Check the Speech component for your language in Windows Settings, " +
                    "and run EDMC as your normal desktop user.");
            string culture = Text(settings, "culture", "");
            RecognizerInfo selected = null;
            foreach (RecognizerInfo item in recognizers)
                if (String.Equals(item.Culture.Name, culture, StringComparison.OrdinalIgnoreCase)) {
                    selected = item; break;
                }
            if (selected == null && !String.IsNullOrWhiteSpace(culture))
                throw new InvalidOperationException("Speech recognition language " + culture + " is not installed.");
            if (selected == null)
                foreach (RecognizerInfo item in recognizers)
                    if (item.Culture.Equals(CultureInfo.CurrentUICulture)) { selected = item; break; }
            if (selected == null) selected = recognizers[0];
            Engine = new SpeechRecognitionEngine(selected);
            string[] phrases = Strings(settings, "phrases");
            if (phrases.Length == 0) throw new InvalidOperationException("No enabled voice phrases were supplied.");
            var builder = new GrammarBuilder();
            builder.Culture = selected.Culture;
            builder.Append(new Choices(phrases));
            Engine.LoadGrammar(new Grammar(builder));
            if (Number(settings, "assistant_dictation", 0) != 0) {
                string[] keywords = Strings(settings, "assistant_keywords");
                var assistant = new GrammarBuilder();
                assistant.Culture = selected.Culture;
                if (keywords.Length > 0)
                    assistant.Append(new Choices(keywords));
                assistant.AppendDictation();
                Engine.LoadGrammar(new Grammar(assistant));
            }
            Engine.EndSilenceTimeout = TimeSpan.FromMilliseconds(180);
            Engine.EndSilenceTimeoutAmbiguous = TimeSpan.FromMilliseconds(350);
            Engine.SpeechRecognized += delegate(object sender, SpeechRecognizedEventArgs args) {
                if (!Speaking && DateTime.UtcNow > QuietUntil)
                    Emit(new { type = "recognized", text = args.Result.Text, confidence = args.Result.Confidence });
            };
            Engine.SpeechRecognitionRejected += delegate(object sender, SpeechRecognitionRejectedEventArgs args) {
                if (!Speaking && DateTime.UtcNow > QuietUntil)
                    Emit(new { type = "rejected", text = args.Result == null ? "" : args.Result.Text,
                        confidence = args.Result == null ? 0 : args.Result.Confidence });
            };
            Engine.RecognizeCompleted += delegate(object sender, RecognizeCompletedEventArgs args) {
                if (args.Error != null) Emit(new { type = "error", message = args.Error.Message });
                Finished.Set();
            };
            if (mode == "emulate") {
                Engine.SetInputToNull();
                foreach (string phrase in Strings(settings, "tests")) {
                    RecognitionResult result = Engine.EmulateRecognize(phrase);
                    Emit(new { type = "emulation", input = phrase, matched = result != null,
                        text = result == null ? "" : result.Text });
                }
                return 0;
            }
            if (mode == "audio_test") {
                using (var stream = new MemoryStream())
                using (var speaker = new SpeechSynthesizer()) {
                    speaker.SelectVoiceByHints(VoiceGender.NotSet, VoiceAge.NotSet, 0, selected.Culture);
                    speaker.SetOutputToWaveStream(stream);
                    speaker.Speak(phrases[0]);
                    speaker.SetOutputToNull();
                    stream.Position = 0;
                    Engine.SetInputToWaveStream(stream);
                    RecognitionResult result = Engine.Recognize(TimeSpan.FromSeconds(15));
                    Emit(new { type = "audio_test", input = phrases[0], matched = result != null,
                        text = result == null ? "" : result.Text,
                        confidence = result == null ? 0 : result.Confidence });
                    return result != null ? 0 : 3;
                }
            }
            if (mode != "listen") throw new InvalidOperationException("Unsupported voice-host mode.");
            try {
                Engine.SetInputToDefaultAudioDevice();
            } catch (Exception error) {
                Emit(new { type = "error", code = waveInGetNumDevs() == 0 ? "no_microphone" : "audio_input_unavailable",
                    message = "Cannot open the Windows default microphone. Connect or enable your microphone, " +
                        "select it as the Windows recording input, then try Listen again. " + error.Message,
                    detail = error.GetType().Name });
                return 1;
            }
            Engine.RecognizeAsync(RecognizeMode.Multiple);
            Emit(new { type = "ready", culture = selected.Culture.Name, name = selected.Name });
            string line;
            while ((line = Console.ReadLine()) != null) {
                var command = Read(line);
                string action = Text(command, "type", "");
                if (action == "stop") break;
                if (action == "speak") {
                    try { Speak(Text(command, "text", ""), command); }
                    catch (Exception error) {
                        Emit(new { type = "warning", message = "Speech reply: " + error.Message });
                    }
                }
            }
            return 0;
        } catch (Exception error) {
            Emit(new { type = "error", message = error.Message, detail = error.GetType().Name });
            return 1;
        } finally {
            if (Engine != null) {
                try { Engine.RecognizeAsyncCancel(); Finished.WaitOne(1500); }
                catch (InvalidOperationException) { }
                Engine.Dispose();
            }
            if (Synth != null) Synth.Dispose();
        }
    }
}
