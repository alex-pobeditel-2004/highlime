# Highlime
Make Sublime Text 3 even more high.

Plugin which changes your current color scheme gradually in real time *(if time is real of course)*  
Demonstration video: https://www.youtube.com/watch?v=W5N5igIRits

## What you need to know before the trip
* **Sublime Text build 3149 or later required** - only "new" `.sublime-color-scheme` format supported 
(all default color schemes and some of user-written)
* It's impossible for now to change color scheme of Sublime Text in-memory.  
So main thing this plugin does is repeatedly rewriting the file with current color scheme modification
(every 0.2 sec by default)
so **you'll better to have an OS installed on a SSD to run Highlime** (or you can set greater `time_iteration_step` for HDD)
* Because of the problem described previously we can't yet make a real disco with this plugin -
we're limited by IO operations speed

## Usage
\* *On Mac use `Cmd ⌘` instead of `Ctrl`*  
1) Turn on some good music
2) While using color scheme which you like the most choose `View -> Highlime -> Get high` or press `Shift+Ctrl+L+S+D`
3) To pause plugin (if you are okay with current colors) choose `View -> Highlime -> Take a nap`
or press `Shift+Ctrl+Y+W+N`
4) To revert changes completely choose `View -> Highlime -> Guys I'm sober` or press `Shift+Ctrl+C+O+P`
or just change current color scheme to another one

## Known issues
* "Take a nap" command does not work if it was called from Command Palette (works only from hot keys / main menu)  
Caused by this bug: https://github.com/sublimehq/sublime_text/issues/3404  
Hope it will be fixed in Sublime Text 4
* With very small values of `time_iteration_step` (depends on your system drive speed and current load) Sublime Text
can throw errors on color scheme load.  
This problem cannot be resolved automatically for now (we have no method to know
if settings were loaded fully before rewriting color scheme file).  
To resolve this issue manually you'll need to try a greater value of `time_iteration_step` in preferences
