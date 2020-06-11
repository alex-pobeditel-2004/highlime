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
CHANGES_CLEARED = False


# Listener to stop the plugin when requested:
class HighlimePauseCommandListener(sublime_plugin.EventListener):

    def on_post_text_command(self, view, command_name, args):
        if command_name == 'highlime_pause':
            global PLUGIN_ACTIVATED
            PLUGIN_ACTIVATED = False


class HighlimeBaseCommand(sublime_plugin.TextCommand):
    def __init__(self, view):
        self.view = view

        global_settings = sublime.load_settings('Preferences.sublime-settings')

        # Initialize scheme paths:
        self.original_scheme_path = global_settings.get('color_scheme')
        original_scheme_name = self.original_scheme_path.split('/')[-1]
        self.new_scheme_abs_path = os.path.join(sublime.packages_path(), 'User', original_scheme_name)
        self.new_scheme_rel_path = '/'.join(('Packages', 'User', original_scheme_name))

        # If modified scheme was already created then just continue to work with it:
        if os.path.isfile(self.new_scheme_abs_path):
            self.original_scheme_path = self.new_scheme_rel_path

        plugin_settings = sublime.load_settings('Highlime.sublime-settings')
        self.color_step = plugin_settings.get('color_iteration_step', 0.0015)
        self.time_step = plugin_settings.get('time_iteration_step', 0.2)


# Command to signalize that we want to stop the plugin:
class HighlimePauseCommand(HighlimeBaseCommand):

    def is_enabled(self):
        """
        Disables or enables the command
        """
        if PLUGIN_ACTIVATED:
            return True
        else:
            return False

    def run(self, edit):
        print('Highlime paused')


# Command to signalize that we want to revert color scheme changes made by the plugin:
class HighlimeResetCommand(HighlimeBaseCommand):

    def is_enabled(self):
        """
        Disables or enables the command
        """
        if not PLUGIN_ACTIVATED and CHANGES_CLEARED:
            return True
        else:
            return False

    def run(self, edit):
        # Remove changed schema file and reload settings:

        with open(self.new_scheme_abs_path, 'w', encoding='utf-8') as new_scheme_file:
            new_scheme_file.write('{}')
        sublime.load_settings('Preferences.sublime-settings')

        print('Highlime stopped and reverted color scheme changes')
        global PLUGIN_ACTIVATED
        PLUGIN_ACTIVATED = False

        global CHANGES_CLEARED
        CHANGES_CLEARED = True


class HighlimeGetHighCommand(HighlimeBaseCommand):

    def is_enabled(self):
        """
        Disables or enables the command
        """
        if PLUGIN_ACTIVATED:
            return False
        else:
            return True

    def run(self, edit):
        # TODO
        #sublime_plugin.reload_plugin('Highlime')
        # Color scheme compatibility check:
        if os.path.splitext(self.original_scheme_path)[1].lower() != '.sublime-color-scheme':
            sublime.error_message("You won't get high with {}\n"
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

        bg_thread = threading.Thread(target=self.make_high, args=(original_scheme,))
        bg_thread.start()


    def create_color_scheme(self):
        """
        Create color scheme file that will supersede current color scheme and apply it
        :return: Paths to the created color scheme
        """
        # Save original scheme at the beginning:
        try:
            original_scheme = sublime.load_resource(self.original_scheme_path)
        except IOError:
            sublime.error_message('Failed to load current color scheme.\n'
                                  'Please, select your color scheme again and retry')
            return False

        # Write original scheme to the new file:
        try:
            with open(self.new_scheme_abs_path, 'w', encoding='utf-8') as new_scheme_file:
                new_scheme_file.write(original_scheme)
        except OSError:
            sublime.error_message('Failed to create color scheme file: {}'.format(self.new_scheme_abs_path))
            return ''

        settings = sublime.load_settings('Preferences.sublime-settings')
        settings.set('color_scheme', self.new_scheme_rel_path)
        sublime.save_settings('Preferences.sublime-settings')

        return original_scheme

    def make_high(self, original_scheme):
        """
        Main function with the color iteration logic
        :return:
        """
        try:
            # Using ast.literal_eval instead of json.loads because of possible trailing commas in color scheme:
            original_scheme_json = ast.literal_eval(original_scheme)
        except (ValueError, SyntaxError) as error:
            sublime.error_message('Failed to read current color scheme:\n{}'.format(error))
            return False

        init_colors = dict()
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
                            return False
                        else:
                            init_colors[section][item] = item_color

        while True:

            # Checking for plugin stop event:
            if not PLUGIN_ACTIVATED:
                break

            result = dict()
            for section in sections:
                result[section] = dict()
                # Iterating through every color we've parsed and changing it    :
                for item in init_colors[section]:
                    init_colors[section][item] = iter_color(init_colors[section][item], self.color_step)
                    result[section][item] = represent_hsla_as_function(init_colors[section][item])
            original_scheme_json.update(result)
            with open(self.new_scheme_abs_path, 'w', encoding='utf-8') as new_scheme_file:
                json.dump(original_scheme_json, new_scheme_file)

            sublime.load_settings('Preferences.sublime-settings')
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
        # Get int numeric values of all channels:
        color_list = [int(x, 16) for x in color_list]

        # TODO Leave only RGBA or HSLA

        # Converting to HSLA:
        color_list_hsla = list(colorsys.rgb_to_hls(*[x / 255 for x in color_list[0:3]]))
        color_list_hsla.append(color_list[-1] / 255)

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
        # Get int numeric values of all channels:
        color_list = [int(x) for x in color_list]

        # TODO Leave only RGBA or HSLA

        # Converting to HSLA:
        color_list_hsla = list(colorsys.rgb_to_hls(*[x / 255 for x in color_list[0:3]]))
        color_list_hsla.append(color_list[-1] / 255)

    # Functional hsl(a) notation:
    elif normalized_color.startswith('hsl'):
        # Grab all arguments from hsl(a) function:
        color_match = re.match(r'^hsl(a)?\((.*?)\)$', normalized_color)
        # Save values to dictionary:
        hsl_values = dict(zip(('h', 's', 'l', 'a'), (float(x.rstrip('%')) for x in color_match.group(2).split(','))))
        # Transform result to rgb(a):
        rgb = colorsys.hls_to_rgb(hsl_values['h'] / 360, hsl_values['l'] / 100, hsl_values['s'] / 100)
        color_list.extend((int(x * 255) for x in rgb))
        # Recalculate or create alpha channel:
        if 'a' not in hsl_values:
            color_list.append(255)
        else:
            color_list.append(float(hsl_values['a']) * 255)

        # TODO Leave only RGBA or HSLA

        # Converting to HSLA:
        color_list_hsla = list(colorsys.rgb_to_hls(*[x / 255 for x in color_list[0:3]]))
        color_list_hsla.append(color_list[-1] / 255)

    if len(color_list_hsla) != 4:
        sublime.error_message('Cannot parse value {} from color scheme'.format(initial_color))
        return []
    else:
        return color_list_hsla


def iter_color(color, step):
    """
    Iterate through given color by the given step
    :param color: 4-component list of HSLA
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
    return 'hsla({0}, {1}%, {2}%, {3})'.format(color[0] * 360, int(color[2] * 100), int(color[1] * 100), color[3])
