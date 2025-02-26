import requests
from bs4 import BeautifulSoup
import gi
import subprocess
import signal
import os
import configparser
import threading
import time

gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, GLib, Notify, Gdk

class SkyrockRadioApp(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Skyrock Radio")
        self.set_default_size(400, 300)  # Taille de la fenêtre

        # Définir l'icône de l'application
        self.set_icon_from_file("play.png")  # Utiliser play.png comme icône de l'application

        # Initialiser les notifications système
        Notify.init("Skyrock Radio")

        # Liste des stations Skyrock (URL simplifiées)
        self.stations = {
            "Skyrock": "https://icecast.skyrock.net/s/natio_mp3_128k",
            "Skyrock 100% Français": "https://icecast.skyrock.net/s/francais_aac_128k",
            "Skyrock La Nocturne": "https://icecast.skyrock.net/s/nocturne_aac_128k",
            "Skyrock PLM": "https://icecast.skyrock.net/s/plm_aac_128k",
            "Skyrock Hit US": "https://icecast.skyrock.net/s/hit_us_aac_128k",
        }

        # Charger les préférences
        self.config_file = os.path.expanduser("~/.skyrock_radio.conf")
        self.config = configparser.ConfigParser()
        self.load_preferences()

        # Créer une boîte verticale pour organiser les widgets
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(self.box)

        # Appliquer un style CSS cyberpunk rouge avec arrière-plan personnalisé
        self.apply_cyberpunk_css()

        # Titre de l'application
        self.title_label = Gtk.Label(label="Skyrock Radio")
        self.title_label.get_style_context().add_class("title")
        self.box.pack_start(self.title_label, False, False, 0)

        # Menu déroulant pour choisir la station
        self.station_combo = Gtk.ComboBoxText()
        for station in self.stations:
            self.station_combo.append_text(station)
        self.station_combo.set_active(self.config.getint("Preferences", "station_index", fallback=0))
        self.station_combo.get_style_context().add_class("combo")
        self.station_combo.connect("changed", self.on_station_changed)
        self.box.pack_start(self.station_combo, False, False, 0)

        # Étiquette pour afficher la chanson en cours
        self.song_label = Gtk.Label(label="Chanson en cours : Inconnue")
        self.song_label.get_style_context().add_class("song-label")
        self.box.pack_start(self.song_label, False, False, 0)

        # Boîte pour organiser le bouton Play et l'étiquette "Play" / "Stop"
        self.play_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.box.pack_start(self.play_box, False, False, 0)

        # Bouton pour démarrer/arrêter la radio avec une icône personnalisée
        self.play_button = Gtk.Button()
        self.play_icon = Gtk.Image.new_from_file("play.png")  # Icône personnalisée
        self.play_button.set_image(self.play_icon)
        self.play_button.get_style_context().add_class("play-button")
        self.play_button.connect("clicked", self.on_play_button_clicked)
        self.play_box.pack_start(self.play_button, False, False, 0)

        # Étiquette pour afficher "Play" ou "Stop" en blanc sous le bouton
        self.play_stop_label = Gtk.Label(label="Play")
        self.play_stop_label.get_style_context().add_class("play-stop-label")
        self.play_stop_label.set_halign(Gtk.Align.CENTER)  # Centrer le texte horizontalement
        self.play_box.pack_start(self.play_stop_label, False, False, 0)

        # Curseur de volume
        self.volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume_scale.set_value(self.config.getfloat("Preferences", "volume", fallback=50))
        self.volume_scale.connect("value-changed", self.on_volume_changed)
        self.volume_scale.get_style_context().add_class("volume-scale")
        self.box.pack_start(self.volume_scale, False, False, 0)

        # Variable pour suivre l'état de la radio
        self.radio_playing = False
        self.process = None
        self.monitor_thread = None
        self.stop_monitoring = False

        # Mettre à jour les informations de la chanson
        GLib.timeout_add_seconds(10, self.update_song_info)

        # Intercepter l'événement de fermeture de la fenêtre
        self.connect("delete-event", self.on_window_delete)

    def apply_cyberpunk_css(self):
        """Applique un style CSS cyberpunk rouge avec arrière-plan personnalisé."""
        css = """
        window {
            background-image: url('skyrock.png');
            background-size: cover;
            background-repeat: no-repeat;
            background-position: center;
            color: #ff0044;
            font-family: 'Courier New', monospace;
        }
        .title {
            font-size: 20px;
            font-weight: bold;
            color: #ff0044;
            text-shadow: 0 0 5px #ff0044;
            animation: glow 2s infinite alternate;
        }
        @keyframes glow {
            from { text-shadow: 0 0 5px #ff0044; }
            to { text-shadow: 0 0 20px #ff0044; }
        }
        .combo {
            background-color: rgba(51, 51, 51, 0.8);
            color: #ff0044;
            border: 1px solid #ff0044;
            border-radius: 5px;
            padding: 5px;
            transition: background-color 0.3s, color 0.3s;
        }
        .combo:hover {
            background-color: rgba(68, 68, 68, 0.8);
            color: #ff3366;
        }
        .song-label {
            font-size: 14px;
            color: #ff0044;
            text-shadow: 0 0 5px #ff0044;
        }
        .play-button {
            background-color: #ff0044;
            color: #000;
            border: none;
            border-radius: 5px;
            padding: 8px 16px;
            font-size: 14px;
            font-weight: bold;
            text-shadow: 0 0 5px #000;
            transition: background-color 0.3s;
        }
        .play-button:hover {
            background-color: #ff3366;
        }
        .play-stop-label {
            font-size: 14px;
            color: white;  /* Texte en blanc */
        }
        .volume-scale {
            background-color: rgba(51, 51, 51, 0.8);
            color: #ff0044;
            border: 1px solid #ff0044;
            border-radius: 5px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def load_preferences(self):
        """Charge les préférences depuis le fichier de configuration."""
        if not os.path.exists(self.config_file):
            self.config["Preferences"] = {"station_index": "0", "volume": "50"}
            self.save_preferences()
        else:
            self.config.read(self.config_file)

    def save_preferences(self):
        """Sauvegarde les préférences dans le fichier de configuration."""
        with open(self.config_file, "w") as f:
            self.config.write(f)

    def on_play_button_clicked(self, button):
        if not self.radio_playing:
            # Démarrer la radio avec VLC
            station_name = self.station_combo.get_active_text()
            station_url = self.stations.get(station_name)
            if station_url:
                try:
                    self.process = subprocess.Popen(
                        ["vlc", "--intf", "dummy", "--no-video", "--volume", str(int(self.volume_scale.get_value())), station_url],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    self.radio_playing = True
                    self.play_stop_label.set_label("Stop")  # Mettre à jour l'étiquette en "Stop"
                    self.play_sound("start_sound.wav")  # Jouer un son de démarrage

                    # Démarrer le thread de surveillance
                    self.stop_monitoring = False
                    self.monitor_thread = threading.Thread(target=self.monitor_process)
                    self.monitor_thread.start()
                except Exception as e:
                    self.show_error_message(f"Erreur : Impossible de démarrer VLC. {str(e)}")
        else:
            # Arrêter la radio
            self.stop_radio()
            self.radio_playing = False
            self.play_stop_label.set_label("Play")  # Mettre à jour l'étiquette en "Play"
            self.play_sound("stop_sound.wav")  # Jouer un son d'arrêt

    def stop_radio(self):
        """Arrête la radio en tuant le processus VLC."""
        if self.process:
            try:
                self.stop_monitoring = True  # Arrêter la surveillance
                self.process.terminate()  # Envoyer SIGTERM
                self.process.wait(timeout=5)  # Attendre la fin du processus
            except subprocess.TimeoutExpired:
                self.process.kill()  # Forcer l'arrêt si nécessaire
            except Exception as e:
                self.show_error_message(f"Erreur : Impossible d'arrêter VLC. {str(e)}")
            finally:
                self.process = None

    def monitor_process(self):
        """Surveille le processus VLC et le redémarre s'il s'arrête."""
        while not self.stop_monitoring:
            if self.process and self.process.poll() is not None:  # Si le processus s'est arrêté
                if not self.stop_monitoring:  # Ne redémarrer que si l'arrêt n'est pas volontaire
                    GLib.idle_add(self.on_play_button_clicked, None)  # Redémarrer la radio
                    break
            time.sleep(1)  # Vérifier toutes les secondes

    def on_station_changed(self, combo):
        """Joue un son lors du changement de station."""
        self.play_sound("station_change.wav")

    def play_sound(self, sound_file):
        """Joue un effet sonore."""
        if os.path.exists(sound_file):
            subprocess.Popen(["aplay", sound_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def on_volume_changed(self, scale):
        """Met à jour le volume en utilisant pactl."""
        volume = int(scale.get_value())
        # Ajuster le volume avec pactl
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"])
        # Sauvegarder le volume dans les préférences
        self.config["Preferences"]["volume"] = str(volume)
        self.save_preferences()

    def update_song_info(self):
        # URL de la page Skyrock Radio
        url = "https://skyrock.fm"
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extraire la chanson en cours (ajustez le sélecteur selon la structure de la page)
            song_info = soup.find('div', class_='now-playing')  # Exemple de sélecteur
            if song_info:
                song_text = song_info.get_text(strip=True)
                self.song_label.set_label(f"Chanson en cours : {song_text}")
                # Afficher une notification système
                self.show_notification("Skyrock Radio", f"Chanson en cours : {song_text}")
        except Exception as e:
            self.show_error_message(f"Erreur : Impossible de récupérer les informations. {str(e)}")

        # Continuer à mettre à jour les informations
        return True

    def on_window_delete(self, window, event):
        """Gère l'événement de fermeture de la fenêtre."""
        # Sauvegarder la station sélectionnée
        self.config["Preferences"]["station_index"] = str(self.station_combo.get_active())
        self.save_preferences()
        self.stop_radio()  # Arrêter la radio
        Gtk.main_quit()  # Quitter l'application

    def show_error_message(self, message):
        """Affiche un message d'erreur dans une boîte de dialogue."""
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()

    def show_notification(self, title, message):
        """Affiche une notification système."""
        notification = Notify.Notification.new(title, message, "media-playback-start")
        notification.show()

# Lancer l'application
win = SkyrockRadioApp()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
