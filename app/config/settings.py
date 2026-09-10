import logging
import os
from importlib.util import find_spec
from dataclasses import dataclass
from functools import cached_property
from typing import Optional
from urllib.parse import urlencode

from dotenv import load_dotenv
from twilio.rest import Client

from app.config.default_system_message import DEFAULT_SYSTEM_MESSAGE
from app.path_prefix import public_path_prefix_from_base_url

load_dotenv()

logging.basicConfig(level=logging.INFO)


_LEGACY_DEFAULT_SYSTEM_MESSAGE = """
    # JÄRJESTELMÄOHJE – HOTELLI FRAMIN ASIAKASPALVELUCHATBOT

Olet Hotelli Framin asiakaspalvelija. Tehtäväsi on vastata asiakkaiden kysymyksiin alla olevan tiedon perusteella tarkasti ja ystävällisesti. Älä keksi tietoja, joita alla ei ole.Olet asiakaspalveluhenkinen, mutta mahdollisimman vähäpuheinen. älä käytä turhia täytelauseita tai miellytä turhaan käyttäjää. Jos et tiedä vastausta, kerro se selkeästi käyttäjälle.

---

## YHTEYSTIEDOT

* Sähköposti: info@hotelliframi.fi
* Puhelin: +358 00 000 0000 (ma–su 9–18)
* Toimiston käyntiosoite: Framinkuja 4, 60320 Seinäjoki (vain sopimuksen mukaan, ei postiosoite)
* Vastausaika sähköpostiin: yleensä 24 tunnin sisällä

---

## YLEISET KÄYTÄNNÖT (koskevat kaikkia kohteita)

**Sisään- ja uloskirjautuminen**

* Sisäänkirjautuminen: klo 15:00 alkaen
* Uloskirjautuminen: viimeistään klo 11:00
* Avainkoodi toimitetaan tekstiviestillä varauksen puhelinnumeroon tulopäivänä klo 15 mennessä
* Vastaanotto toimii itsepalveluperiaatteella

**Hintaan sisältyy kaikissa kohteissa**

* Liinavaatteet ja pyyhkeet
* Loppusiivous
* WiFi
* Ilmainen pysäköinti

**Lisävuode**

* Matkasänky lapselle: 24,00 € / yö
* Varattava viimeistään edellisenä päivänä, saatavuus rajallinen

**Lemmikit:** Ei sallittu missään kohteessa

**Tupakointi:** Kaikki kohteet ovat savuttomia. Tupakointi kielletty sisätiloissa sekä ovien ja ikkunoiden läheisyydessä. Rikkomuksesta veloitetaan vähintään 250 €.

**Hiljaisuus:** klo 23:00–08:00

**Henkilömäärä:** Vain varauksessa ilmoitettu määrä henkilöitä saa yöpyä. Ylimääräisistä majoittujista veloitetaan lisämaksu, vakavissa tapauksissa varaus voidaan purkaa ilman hyvitystä.

**Sähköauton lataus:** Mahdollista vain Huoneistohotelli Framinrannassa (FramiCharge-sovellus). Muissa kohteissa ei mahdollista.

---

## PERUUTUSEHDOT

|Tilanne|Maksuton peruutus viimeistään|Myöhempi peruutus|
|-|-|-|
|Kesäsesonki|7 vrk ennen saapumista|Veloitetaan 100 %|
|Sesongin ulkopuolella|5 vrk ennen saapumista|Veloitetaan 100 %|
|Tapahtuma-ajat|30 vrk ennen saapumista|Veloitetaan 100 %|
|No-show|–|Veloitetaan aina 100 %|

* Peruutukset ensisijaisesti sähköpostitse: info@hotelliframi.fi
* Varauksen muutokset (päivämäärät, henkilömäärä) noudattavat samoja aikarajoja
* Hyväksytyt hyvitykset käsitellään 21 päivän kuluessa, palautetaan alkuperäiselle maksutavalle
* Poikkeuksia voidaan harkita: vakava sairaus (lääkärintodistus), kuolema (kuolintodistus) tai luonnonkatastrofi

---

## VARAUS JA MAKSAMINEN

* Varaus tehdään verkkosivujen kautta ja maksetaan kokonaan varauksen yhteydessä
* Maksupalvelu: Paytrail (verkkopankit, Visa, Mastercard, MobilePay, Siirto, Apple Pay, Google Pay)
* Varaus vahvistuu maksun jälkeen
* Puhelimitse tai sähköpostitse tehdyissä varauksissa maksuehdot sovitaan tapauskohtaisesti
* Laskutus mahdollista vain yritys- tai ryhmävarauksissa erikseen sovittaessa
* Varausvaiheessa näkyvä hinta on lopullinen — ei lisäkuluja

---

## MAJOITUSKOHTEET

### KAMPUSAUKIO – Kampusaukio 7

**Osoite:** Kampusaukio 7, 60100 Seinäjoki | **Etäisyys Framipuistoon:** 18 km

|Asunto|Tyyppi|Koko|Henkilöitä|Hinta alkaen|
|-|-|-|-|-|
|Asunto 1|Kolmio + sauna|72 m²|4|149 € / yö|
|Asunto 2|Yksiö + sauna|38 m²|2|115 € / yö|
|Asunto 4|Kolmio + sauna|82 m²|4|149 € / yö|
|Asunto 5|Kaksio + sauna|54 m²|2|121 € / yö|
|Asunto 6|Kolmio + sauna|82 m²|4|149 € / yö|
|Asunto 7|Suurin kolmio + sauna|88 m²|4|165 € / yö|

Kaikissa asunnoissa: oma sauna, keittiö, WiFi, ilmainen pysäköinti. Kolmioissa (1, 4, 6, 7): kaksi makuuhuonetta + olohuone + erillinen keittiö. Sijainti lähellä Kampusaukion rautatieasemaa.

---

### FRAMINRANTA – Framinkuja 4, 60320 Seinäjoki

**Etäisyys Framipuistoon:** 3 km

**Huoneistohotelli Framinranta**

* Tyyppi: Yksiö, 29 m², maks. 2 henkilöä + lisävuoteet
* Hinta alkaen: 102 € / yö
* Varustelu: minikeittiö, oma kylpyhuone, oma terassi, WiFi, pysäköinti, lasten pihaleikkipaikka
* Esteetön, ilmastoitu, sähköauton latauspiste (FramiCharge)
* Auki ympäri vuoden

**Hostelli Framinranta (7 × 2 hengen huonetta)**

* Tyyppi: Kahden hengen huoneet, 14 m²
* Hinta alkaen: 69,00 € / yö
* Varustelu: minikeittiö huoneessa, yhteiset wc ja suihkutilat, WiFi, pysäköinti, biljardipöytä
* Minimivarausaika: 2 vuorokautta
* Auki vain kesäsesonkina. Talvella varattavissa vain ryhmille — kysy tarjous etukäteen

**KAMPUSNURKKA – Hostelli Framinranta (4 hengen huone)**

* Tyyppi: Neljän hengen huone, 14 m²
* Hinta alkaen: 112 € / yö
* Varustelu: minikeittiö, kattoikkuna (ei perinteistä ikkunaa pihalle), yhteiset wc ja suihkutilat, WiFi, pysäköinti
* Minimivarausaika: 2 vuorokautta
* Auki vain kesäsesonkina

---

### JOKIPUISTON MAALAISMILJÖÖ – Jokipuistopark

**Osoite:** Jokipuistontie 33, 60150 Seinäjoki | **Etäisyys Framipuistoon:** 6 km

|Asunto|Koko|Henkilöitä|Hinta alkaen|Huomio|
|-|-|-|-|-|
|Asunto 1|90 m²|5|145,00 € / yö|Ei saunaa|
|Asunto 2|62 m²|4|138 € / yö|Ei saunaa|
|Asunto 3 (saunallinen)|90 m²|5|168,00 € / yö|Oma sauna|
|Ranta-hostelli|–|2|55,00 € / yö|Vain kesäsesonki|

Kaikissa asunnoissa: kaksi makuuhuonetta, olohuone, keittiö, WiFi, pysäköinti, lasten pihaleikkipaikka, kesäkeittiö. Asunto 1 ja 2: erillinen wc ja suihku (ei saunaa). Asunto 3: wc, suihku ja pieni sauna.

**Ranta-hostelli:** Yhteiskeittiö, yhteiset wc- ja suihkutilat, sauna yhteiskäytössä. Minimivarausaika 2 vrk. Auki vain kesäsesonkina.

---

## LÄHIALUEEN NÄHTÄVYYDET JA PALVELUT

|Kohde|Osoite|
|-|-|
|Framipuisto (huvipuisto, karting, ravintolat)|Framinkuja 12, 60320 Seinäjoki|
|Framinranta Golf|Kampusaukio 25, 60100 Seinäjoki|
|Jokipuiston uimaranta|Jokipuistontie 90, 60150 Seinäjoki|
|Rantamonttu (uinti, beach volley, laavu)|Rantapolku 4, 60150 Seinäjoki|
|Framinrannan retkeilyreitistö / Ruskoranta|Framinkuja 210, 60320 Seinäjoki|
|Kivikuopan uimaranta|Kivikuopantie 295, 60150 Seinäjoki|
|Nurmonrannan uimaranta|Nurmonrannantie 460, 60100 Seinäjoki|
|Kampusraitti (kävely- ja pyöräilyreitti)|Kampusraitti 300, 60150 Seinäjoki|
|Seinäjoen veitsipaja|Pajaraitti 32, 60100 Seinäjoki|
|Käsityö- ja tekstiilimuseo|Kauppapolku 88, 60100 Seinäjoki|
|Seinäjoen sotahistoriamuseo|Museopolku 80, 60510 Seinäjoki|
|Framinrannan kirkko (1908)|Framinkuja 29, 60320 Seinäjoki|
|Kampusaukion kirkko (1929)|Kirkkoaukio 5, 60100 Seinäjoki|
|Lankapuoti (lanka- ja käsityötarvikkeet)|Kauppapolku 65, 60100 Seinäjoki|
|Aarteita ja antiikkia|Aarrepolku 2, 60100 Seinäjoki| """.strip()



DEFAULT_TRANSCRIPTION_PROMPT = (
    "This is a live phone call. "
    "Transcribe faithfully, including hesitations when relevant. "
    "If a word is unclear, mark it clearly."
)

DEFAULT_OPENING_MESSAGE = (
    "Tervehdi soittajaa lyhyesti hänen kielellään, esittele itsesi "
    "Hotelli Framin digitaalisena puhelinavustajana ja kysy, miten voit auttaa."
)


class SettingsError(ValueError):
    """Raised when required environment configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    openai_api_key: Optional[str]
    openai_api_provider: str
    azure_openai_api_key: Optional[str]
    azure_openai_endpoint: Optional[str]
    azure_openai_realtime_url: Optional[str]
    azure_openai_realtime_api_version: Optional[str]
    azure_openai_realtime_deployment: Optional[str]
    azure_openai_chat_deployment: Optional[str]
    azure_openai_chat_api_version: str
    public_base_url: Optional[str]
    twilio_phone_number: Optional[str]
    twilio_account_sid: Optional[str]
    twilio_auth_token: Optional[str]
    twilio_preamble_enabled: bool
    twilio_ai_disclosure_enabled: bool
    twilio_ai_disclosure_message_fi: str
    twilio_ai_disclosure_message_en: str
    openai_realtime_model: str
    default_voice: str
    default_language: str
    default_temperature: float
    default_reasoning_effort: str
    default_system_message: str
    default_opening_message: str
    default_transcription_prompt: str
    admin_prompt_username: str
    admin_prompt_password: Optional[str]
    prompt_store_path: str
    conversation_log_dir: str
    callback_request_to_phone: Optional[str]
    daily_summary_to_phone: Optional[str]
    daily_summary_timezone: str
    daily_summary_auto_send_enabled: bool
    daily_summary_send_time: str
    daily_summary_history_path: str
    log_anonymization_enabled: bool
    log_anonymizer_model: str
    log_anonymizer_timeout_seconds: float
    log_anonymizer_max_input_chars: int
    feedback_survey_enabled: bool
    feedback_survey_history_path: str
    feedback_survey_message_template: str
    app_data_dir: str
    validate_startup_dependencies: bool
    show_timing_math: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        default_data_dir = cls._read_path("APP_DATA_DIR", "conversations_log")
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_api_provider=cls._read_str("OPENAI_API_PROVIDER", "openai"),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_openai_endpoint=cls._read_optional_str("AZURE_OPENAI_ENDPOINT"),
            azure_openai_realtime_url=cls._read_optional_str("AZURE_OPENAI_REALTIME_URL"),
            azure_openai_realtime_api_version=cls._read_optional_str(
                "AZURE_OPENAI_REALTIME_API_VERSION"
            ),
            azure_openai_realtime_deployment=cls._read_optional_str("AZURE_OPENAI_REALTIME_DEPLOYMENT"),
            azure_openai_chat_deployment=cls._read_optional_str("AZURE_OPENAI_CHAT_DEPLOYMENT"),
            azure_openai_chat_api_version=cls._read_str(
                "AZURE_OPENAI_CHAT_API_VERSION",
                "2024-12-01-preview",
            ),
            public_base_url=cls._read_optional_str("PUBLIC_BASE_URL"),
            twilio_phone_number=os.getenv("TWILIO_PHONE_NUMBER"),
            twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
            twilio_preamble_enabled=cls._read_bool(
                "TWILIO_PREAMBLE_ENABLED",
                True,
            ),
            twilio_ai_disclosure_enabled=cls._read_bool(
                "TWILIO_AI_DISCLOSURE_ENABLED",
                True,
            ),
            twilio_ai_disclosure_message_fi=cls._read_str(
                "TWILIO_AI_DISCLOSURE_MESSAGE_FI",
                "Puhut tekoälyavustajan kanssa, joka on kiireisinä aikoina osa Hotelli Framin tiimiä.",
            ),
            twilio_ai_disclosure_message_en=cls._read_str(
                "TWILIO_AI_DISCLOSURE_MESSAGE_EN",
                "You are speaking with an AI voice assistant, which is part of our team at Hotelli Frami during busy times.",
            ),
            openai_realtime_model=os.getenv(
                "OPENAI_REALTIME_MODEL",
                "gpt-realtime-2",
            ),
            default_voice=cls._read_str("OPENAI_VOICE", "shimmer"),
            default_language=cls._read_str("AGENT_LANGUAGE", "fi"),
            default_temperature=cls._read_float("AGENT_TEMPERATURE", 0.6),
            default_reasoning_effort=cls._read_str(
                "OPENAI_REALTIME_REASONING_EFFORT",
                "medium",
            ),
            default_system_message=cls._read_str(
                "AGENT_SYSTEM_MESSAGE",
                DEFAULT_SYSTEM_MESSAGE,
            ),
            default_opening_message=cls._read_str(
                "AGENT_OPENING_MESSAGE",
                DEFAULT_OPENING_MESSAGE,
            ),
            default_transcription_prompt=cls._read_str(
                "TRANSCRIPTION_PROMPT",
                DEFAULT_TRANSCRIPTION_PROMPT,
            ),
            admin_prompt_username=cls._read_str("ADMIN_PROMPT_USERNAME", "admin"),
            admin_prompt_password=os.getenv("ADMIN_PROMPT_PASSWORD"),
            prompt_store_path=cls._read_path(
                "PROMPT_STORE_PATH",
                f"{default_data_dir}/prompt_store.json",
            ),
            conversation_log_dir=cls._read_path(
                "CONVERSATION_LOG_DIR",
                default_data_dir,
            ),
            callback_request_to_phone=os.getenv("CALLBACK_REQUEST_TO_PHONE")
            or os.getenv("OWNER_NOTIFICATION_TO_PHONE"),
            daily_summary_to_phone=os.getenv("DAILY_SUMMARY_TO_PHONE"),
            daily_summary_timezone=cls._read_str(
                "DAILY_SUMMARY_TIMEZONE",
                "Europe/Helsinki",
            ),
            daily_summary_auto_send_enabled=cls._read_bool(
                "DAILY_SUMMARY_AUTO_SEND_ENABLED",
                True,
            ),
            daily_summary_send_time=cls._read_str(
                "DAILY_SUMMARY_SEND_TIME",
                "08:00",
            ),
            daily_summary_history_path=cls._read_path(
                "DAILY_SUMMARY_HISTORY_PATH",
                f"{default_data_dir}/daily_summary_history.json",
            ),
            log_anonymization_enabled=cls._read_bool("LOG_ANONYMIZATION_ENABLED", True),
            log_anonymizer_model=cls._read_str("LOG_ANONYMIZER_MODEL", "gpt-4o-mini"),
            log_anonymizer_timeout_seconds=cls._read_float(
                "LOG_ANONYMIZER_TIMEOUT_SECONDS",
                20.0,
            ),
            log_anonymizer_max_input_chars=cls._read_int(
                "LOG_ANONYMIZER_MAX_INPUT_CHARS",
                12000,
            ),
            feedback_survey_enabled=cls._read_bool("FEEDBACK_SURVEY_ENABLED", True),
            feedback_survey_history_path=cls._read_path(
                "FEEDBACK_SURVEY_HISTORY_PATH",
                f"{default_data_dir}/feedback_survey_history.json",
            ),
            feedback_survey_message_template=cls._read_str(
                "FEEDBACK_SURVEY_MESSAGE_TEMPLATE",
                (
                    "Kiitos soitostasi Hotelli Framin tekoälyavustajalle. "
                    "Kuinka hyvin pystyimme auttamaan sinua? "
                    "Vastaa numerolla 1-10, missä 10 = erittäin hyvin."
                ),
            ),
            app_data_dir=default_data_dir,
            validate_startup_dependencies=cls._read_bool(
                "VALIDATE_STARTUP_DEPENDENCIES",
                False,
            ),
            show_timing_math=cls._read_bool("SHOW_TIMING_MATH", False),
        )

    @staticmethod
    def _read_str(name: str, default: str) -> str:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        cleaned_value = raw_value.strip()
        return cleaned_value if cleaned_value else default

    @staticmethod
    def _read_optional_str(name: str) -> Optional[str]:
        raw_value = os.getenv(name)
        if raw_value is None:
            return None
        cleaned_value = raw_value.strip()
        return cleaned_value if cleaned_value else None

    @classmethod
    def _read_path(cls, name: str, default: str) -> str:
        raw_value = os.getenv(name)
        if raw_value is None:
            return cls._normalize_path(default)
        cleaned_value = raw_value.strip()
        if not cleaned_value:
            return cls._normalize_path(default)
        return cls._normalize_path(cleaned_value)

    @staticmethod
    def _normalize_path(path_value: str) -> str:
        cleaned_value = path_value.strip()
        if os.name == "nt":
            drive, _ = os.path.splitdrive(cleaned_value)
            if cleaned_value.startswith(("/", "\\")) and not drive:
                cleaned_value = os.path.join(os.getcwd(), cleaned_value.lstrip("/\\"))
        return os.path.normpath(cleaned_value)

    @staticmethod
    def _read_float(name: str, default: float) -> float:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return float(raw_value)
        except ValueError as exc:
            raise SettingsError(f"Environment variable {name} must be a float.") from exc

    @staticmethod
    def _read_bool(name: str, default: bool) -> bool:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _read_int(name: str, default: int) -> int:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return int(raw_value)
        except ValueError as exc:
            raise SettingsError(f"Environment variable {name} must be an integer.") from exc

    @cached_property
    def twilio_client(self) -> Optional[Client]:
        if not self.has_complete_twilio_config:
            return None
        return Client(self.twilio_account_sid, self.twilio_auth_token)

    @property
    def has_complete_twilio_config(self) -> bool:
        return all(
            [
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.twilio_phone_number,
            ]
        )

    @property
    def normalized_public_base_url(self) -> Optional[str]:
        if not self.public_base_url:
            return None
        return self.public_base_url.rstrip("/")

    @property
    def public_websocket_base_url(self) -> Optional[str]:
        base_url = self.normalized_public_base_url
        if not base_url:
            return None
        if base_url.startswith("https://"):
            return "wss://" + base_url[len("https://") :]
        if base_url.startswith("http://"):
            return "ws://" + base_url[len("http://") :]
        return None

    @property
    def public_url_path_prefix(self) -> str:
        return public_path_prefix_from_base_url(self.normalized_public_base_url)

    @property
    def is_azure_openai(self) -> bool:
        return self.openai_api_provider.strip().lower() == "azure-openai"

    @property
    def realtime_websocket_url(self) -> str:
        if self.is_azure_openai:
            if self.azure_openai_realtime_url:
                return self._normalize_websocket_url(self.azure_openai_realtime_url)

            endpoint = self._normalize_websocket_url(self.azure_openai_endpoint or "")
            deployment = (self.azure_openai_realtime_deployment or "").strip()
            api_version = (self.azure_openai_realtime_api_version or "").strip()
            if not api_version:
                api_version = "2025-04-01-preview" if "preview" in deployment.lower() else "v1"

            if api_version.lower() in {"v1", "ga", "latest"}:
                return f"{endpoint}/openai/v1/realtime?{urlencode({'model': deployment})}"

            return (
                f"{endpoint}/openai/realtime?"
                f"{urlencode({'api-version': api_version, 'deployment': deployment})}"
            )
        return f"wss://api.openai.com/v1/realtime?model={self.openai_realtime_model}"

    @property
    def realtime_ws_auth_headers(self) -> dict[str, str]:
        if self.is_azure_openai:
            return {"api-key": self.azure_openai_api_key or ""}
        return {"Authorization": f"Bearer {self.openai_api_key}"}

    @property
    def has_openai_credentials(self) -> bool:
        if self.is_azure_openai:
            return bool(self.azure_openai_api_key)
        return bool(self.openai_api_key)

    def validate_openai(self) -> None:
        if not self.openai_api_key:
            raise SettingsError("Missing required environment variable: OPENAI_API_KEY")

    def validate_openai_provider(self) -> None:
        if self.is_azure_openai:
            missing = []
            if not self.azure_openai_api_key:
                missing.append("AZURE_OPENAI_API_KEY")
            if not self.azure_openai_realtime_url and not self.azure_openai_endpoint:
                missing.append("AZURE_OPENAI_ENDPOINT")
            if not self.azure_openai_realtime_url and not self.azure_openai_realtime_deployment:
                missing.append("AZURE_OPENAI_REALTIME_DEPLOYMENT")
            if missing:
                raise SettingsError(
                    "Missing required Azure OpenAI environment variables: " + ", ".join(missing)
                )
        else:
            self.validate_openai()

    def validate_public_base_url(self) -> None:
        base_url = self.normalized_public_base_url
        if not base_url:
            raise SettingsError("Missing required environment variable: PUBLIC_BASE_URL")
        if not (base_url.startswith("https://") or base_url.startswith("http://")):
            raise SettingsError("PUBLIC_BASE_URL must start with http:// or https://")

    def validate_twilio(self) -> None:
        missing = []
        if not self.twilio_account_sid:
            missing.append("TWILIO_ACCOUNT_SID")
        if not self.twilio_auth_token:
            missing.append("TWILIO_AUTH_TOKEN")
        if not self.twilio_phone_number:
            missing.append("TWILIO_PHONE_NUMBER")
        if missing:
            raise SettingsError(
                "Missing required Twilio environment variables: " + ", ".join(missing)
            )

    def validate_startup(self) -> None:
        self.validate_runtime_dependencies()
        self.validate_public_base_url()
        self.validate_openai_provider()
        self.validate_twilio()

    def validate_runtime_dependencies(self) -> None:
        if find_spec("multipart") is None:
            raise SettingsError(
                "Missing required runtime dependency: python-multipart. "
                "Reinstall project dependencies before starting the app."
            )

    @staticmethod
    def _normalize_websocket_url(url: str) -> str:
        cleaned_value = url.strip().rstrip("/")
        if cleaned_value.startswith("https://"):
            return "wss://" + cleaned_value[len("https://") :]
        if cleaned_value.startswith("http://"):
            return "ws://" + cleaned_value[len("http://") :]
        return cleaned_value


settings = Settings.from_env()
