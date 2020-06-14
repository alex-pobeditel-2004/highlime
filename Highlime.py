import sublime
import sublime_plugin

import ast
import colorsys
import json
import os
import re
import threading
import time

PLUGIN_ACTIVATED = False
CHANGES_TO_CLEAR = ''


class HighlimePauseCommandListener(sublime_plugin.EventListener):
    """
    Listener to stop the plugin when requested
    """

    @staticmethod
    def on_post_window_command(view, command_name, args):
        if command_name == 'highlime_pause':
            global PLUGIN_ACTIVATED
            PLUGIN_ACTIVATED = False


class HighlimeBaseCommand(sublime_plugin.WindowCommand):
    def __init__(self, view):
        self.view = view

        # These attributes will be set by the enrich_self method:
        self.original_scheme_path = None
        self.new_scheme_abs_path = None
        self.new_scheme_rel_path = None

        self.settings = self.enrich_self()

        plugin_settings = sublime.load_settings('Highlime.sublime-settings')
        self.color_step = plugin_settings.get('color_iteration_step', 0.0015)
        self.time_step = plugin_settings.get('time_iteration_step', 0.2)

    def enrich_self(self):
        """
        Helper method to get needed paths from preferences and Packages directory
        :return: settings object
        """
        settings = sublime.load_settings('Preferences.sublime-settings')

        # Initialize scheme paths:
        self.original_scheme_path = settings.get('color_scheme')
        original_scheme_name = self.original_scheme_path.split('/')[-1]
        self.new_scheme_abs_path = os.path.join(sublime.packages_path(), 'User', original_scheme_name)
        self.new_scheme_rel_path = '/'.join(('Packages', 'User', original_scheme_name))

        # If modified scheme was already created (but is not empty) then just continue to work with it:
        self.original_scheme_path = self.check_changes()

        return settings

    def check_changes(self):
        """
        Check if new scheme is empty or does not exist yet
        :return: Relative path to original color scheme
        """
        if os.path.isfile(self.new_scheme_abs_path):
            with open(self.new_scheme_abs_path, 'r', encoding='utf-8') as new_scheme:
                global CHANGES_TO_CLEAR
                if new_scheme.read() == '{}':
                    CHANGES_TO_CLEAR = ''
                    return self.original_scheme_path
                else:
                    CHANGES_TO_CLEAR = self.new_scheme_abs_path
                    return self.new_scheme_rel_path
        else:
            return self.original_scheme_path


class HighlimePauseCommand(HighlimeBaseCommand):
    """
    Command to signalize that we want to stop the plugin
    """

    @staticmethod
    def is_enabled():
        """
        Disables or enables the command
        """
        if PLUGIN_ACTIVATED:
            return True
        else:
            return False

    @staticmethod
    def run():
        """
        The only meaning of this function is to trigger HighlimePauseCommandListener
        """
        print('Highlime paused')


class HighlimeResetCommand(HighlimeBaseCommand):
    """
    Command to signalize that we want to revert color scheme changes made by the plugin
    """

    @staticmethod
    def is_enabled():
        """
        Disables or enables the command
        """
        if CHANGES_TO_CLEAR:
            return True
        else:
            return False

    @staticmethod
    def run():
        # Stopping the plugin if it was running:
        global CHANGES_TO_CLEAR
        global PLUGIN_ACTIVATED
        PLUGIN_ACTIVATED = False

        # Clean changed schema file and reload settings:
        with open(CHANGES_TO_CLEAR, 'w', encoding='utf-8') as new_scheme_file:
            new_scheme_file.write('{}')
        sublime.load_settings('Preferences.sublime-settings')

        print('Highlime stopped and reverted color scheme changes')

        CHANGES_TO_CLEAR = ''


class HighlimeGetHighCommand(HighlimeBaseCommand):
    """
    Main plugin command
    """

    @staticmethod
    def is_enabled():
        """
        Disables or enables the command
        """
        if PLUGIN_ACTIVATED:
            return False
        else:
            return True

    def run(self):
        # Get current color scheme paths on every run:
        self.settings = self.enrich_self()

        # Color scheme compatibility check:
        if os.path.splitext(self.original_scheme_path)[1].lower() != '.sublime-color-scheme':
            sublime.error_message("You won't get any high with {}\n"
                                  "Only .sublime-color-scheme format is supported".format(self.original_scheme_path))
            return False
        # Sublime Text version check:
        if int(sublime.version()) < 3149:
            sublime.error_message('This plugin works only with Sublime Text build 3149 and later, '
                                  'your build {} is too old'.format(sublime.version()))
            return False

        original_scheme = self.create_color_scheme()
        if not original_scheme:
            return False

        global PLUGIN_ACTIVATED
        PLUGIN_ACTIVATED = True
        print('Highlime started')

        # Start main functionality in the separate thread
        bg_thread = threading.Thread(target=self.make_high, args=(original_scheme,))
        bg_thread.start()

    def create_color_scheme(self):
        """
        Create color scheme file that will supersede current color scheme
        :return: Paths to the created color scheme
        """
        # Save original scheme at the beginning:
        try:
            original_scheme = sublime.load_resource(self.original_scheme_path)
            # Removing the comments:
            original_scheme = re.sub(r'\s*//.*', '', original_scheme)
        except IOError:
            sublime.error_message('Failed to load current color scheme.\n'
                                  'Please, select your color scheme again and retry.\n'
                                  "Restart Sublime Text if it didn't help")
            return False

        # Write original scheme to the new file:
        try:
            with open(self.new_scheme_abs_path, 'w', encoding='utf-8') as new_scheme_file:
                new_scheme_file.write(original_scheme)
        except OSError:
            sublime.error_message('Failed to create color scheme file: {}'.format(self.new_scheme_abs_path))
            return ''

        global CHANGES_TO_CLEAR
        CHANGES_TO_CLEAR = self.new_scheme_abs_path

        return original_scheme

    def make_high(self, original_scheme):
        """
        Main function with the color iteration logic
        :return: Nothing serious
        """
        try:
            # Using ast.literal_eval instead of json.loads because of possible trailing commas in color scheme:
            original_scheme_json = ast.literal_eval(original_scheme)
        except (ValueError, SyntaxError) as error:
            sublime.error_message('Failed to read current color scheme:\n{}'.format(error))
            return False
        init_colors = dict()

        # Changing colors only in sections in which we are sure:
        sections = ('variables', 'globals')
        for section in sections:
            init_colors[section] = dict()
            if original_scheme_json.get(section, None):
                for item in original_scheme_json[section]:
                    # Checking if value looks like valid color:
                    if re.match(r'^(#|rgb(a)?\(|hsl(a)?\()', original_scheme_json[section][item]):
                        # Get normalized value of the color:
                        item_color = parse_color(original_scheme_json[section][item])
                        if not item_color:
                            pass
                        else:
                            init_colors[section][item] = item_color

        # Infinite trip:
        while True:
            # Check if color scheme was changed by the user:
            if self.new_scheme_rel_path.split('/')[-1] != self.settings.get('color_scheme').split('/')[-1]:
                self.check_changes()
                # Execute scheme reset:
                window = sublime.Window(sublime.active_window().id())
                window.run_command('highlime_reset')
                break
            # Checking for plugin pause event:
            if not PLUGIN_ACTIVATED:
                # In case if we used reset - stop iterating, in case of pause - be idle
                if not CHANGES_TO_CLEAR:
                    break
                else:
                    continue

            result = dict()
            for section in sections:
                result[section] = dict()
                # Iterating through every color we've parsed and changing it:
                for item in init_colors[section]:
                    init_colors[section][item] = iter_color(init_colors[section][item], self.color_step)
                    result[section][item] = represent_hsla_as_function(init_colors[section][item])

            with open(self.new_scheme_abs_path, 'w', encoding='utf-8') as new_scheme_file:
                json.dump(result, new_scheme_file)

            # Load settings to apply color scheme changes and to check if color scheme changed
            self.settings = sublime.load_settings('Preferences.sublime-settings')
            time.sleep(self.time_step)

        return True


def parse_color(initial_color):
    """
    Parse color specified in these forms:
    Hex RGB:    #AABBCC
    Hex RGBA:   #AABBCCDD
    Func RGB:   rgb(0, 0, 0)
    Func RGBA:  rgba(0, 0, 0, 0)
    Func HSL:   hsl(0, 0%, 0%)
    Func HSLA:  hsla(0, 0%, 0%, 0)
    CSS COLORS ARE NOT SUPPORTED
    :param initial_color: String with color code
    :return: List with color code in HSLA notation
    """
    # Strip spaces and force lowercase
    normalized_color = initial_color.replace(' ', '').lower()
    color_list = []

    # Hex rgb(a) notation
    if normalized_color.startswith('#'):
        normalized_color = normalized_color.lstrip('#')
        if len(normalized_color) in (3, 4):
            # Short notation (ABC or ABCD) - normalizing values length:
            color_list.extend((c * (3 - len(c)) for c in normalized_color))
            # Adding alpha channel if absent:
            if len(color_list) == 3:
                color_list.append('ff')
        elif len(normalized_color) in (6, 8):
            # AABBCC or AABBCCDD notation - splitting values by groups of 2:
            color_list.extend((normalized_color[i:i + 2] for i in range(0, len(normalized_color), 2)))
            # Adding alpha channel if absent:
            if len(color_list) == 3:
                color_list.append('ff')
        # Get int numeric values of all channels (RGBA at the moment):
        color_list = [int(x, 16) for x in color_list]

        color_list_hsla = get_hsla_from_rgb(color_list)

    # Functional rgb(a) notation:
    elif normalized_color.startswith('rgb'):
        color_match = re.match(r'^rgb(a)?\((.*?)\)$', normalized_color)
        if color_match.group(2):
            color_list.extend((float(x) for x in color_match.group(2).split(',')))
            # Recalculate or create alpha channel:
            if len(color_list) == 3:
                color_list.append(255)
            elif len(color_list) == 4:
                color_list[3] = color_list[3] * 255
        # Get int numeric values of all channels (RGBA at the moment):
        color_list = [int(x) for x in color_list]

        color_list_hsla = get_hsla_from_rgb(color_list)

    # Functional hsl(a) notation:
    elif normalized_color.startswith('hsl'):
        # Grab all arguments from hsl(a) function:
        color_match = re.match(r'^hsl(a)?\((.*?)\)$', normalized_color)
        # Save values to dictionary:
        hsl_values = dict(zip(('h', 's', 'l', 'a'), (float(x.rstrip('%')) for x in color_match.group(2).split(','))))
        # Transform result to rgb(a):
        rgb = colorsys.hls_to_rgb(hsl_values['h'] / 360, hsl_values['l'] / 100, hsl_values['s'] / 100)
        color_list.extend((int(x * 255) for x in rgb))
        # Recalculate or create alpha channel for RGB:
        if 'a' not in hsl_values:
            color_list.append(255)
        else:
            color_list.append(float(hsl_values['a']) * 255)

        # Save HSLA almost "as-is":
        color_list_hsla = [
            hsl_values['h'] / 360,
            hsl_values['s'] / 100,
            hsl_values['l'] / 100,
            hsl_values.get('a', 1)
        ]
    else:
        print('Cannot parse value {} from color scheme'.format(initial_color))
        return []

    return color_list_hsla


def get_hsla_from_rgb(color_list):
    """
    Simple function for translation of RGBA to HSLA
    :param color_list: 4-component list [R, G, B, A]
    :return: List of colors in [H, S, L, A] format
    """
    # Converting to HSLA:
    color_list_hsla = list(colorsys.rgb_to_hls(*[x / 255 for x in color_list[0:3]]))
    color_list_hsla.append(color_list[-1] / 255)
    # Swap Lightness/Saturation:
    color_list_hsla[1], color_list_hsla[2] = color_list_hsla[2], color_list_hsla[1]

    return color_list_hsla


def iter_color(color, step):
    """
    Iterate through given color by the given step
    :param color: 4-component list [H, S, L, A]
    :param step: Step to iterate hue
    :return: Modified list
    """
    color[0] += step
    if color[0] > 1:
        color[0] = 0

    return color


def represent_hsla_as_function(color):
    """
    Convert color from HSLA list to the hsla(a, b, c, d) format
    :param color: HSLA parameters list
    :return: Color function string
    """
    return 'hsla({0}, {1}%, {2}%, {3})'.format(color[0] * 360, int(color[1] * 100), int(color[2] * 100), color[3])
