
import os
import sys

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, GdkX11

import terra.terra_utils as terra_utils
from terra.ConfigManager import ConfigManager
from terra.handlers import TerraHandler
from terra.handlers import t
from terra.interfaces.InputDialog import InputDialog
from terra.VteObjectContainer import VteObjectContainer
from terra.VteObject import VteObject


class TerminalWin(Gtk.Window):
    def __init__(self, name, monitor):
        main_ui_file = os.path.join(TerraHandler.get_resources_path(), 'main.ui')
        if not os.path.exists(main_ui_file):
            msg = t('UI data file is missing: {}')
            sys.exit(msg.format(main_ui_file))

        super(TerminalWin, self).__init__()

        self.set_keep_above(True)

        self.builder = Gtk.Builder()
        self.builder.set_translation_domain('terra')
        self.builder.add_from_file(main_ui_file)

        self.name = name
        self.screen_id = int(name.split('-')[2])
        # Allow UI to be updated by other events.
        TerraHandler.add_ui_event_handler(self.update_ui)

        self.screen = self.get_screen()
        self.screen.connect('monitors-changed', lambda w: self.check_visible())
        self.monitor = monitor

        self.init_transparency()
        self.init_ui()
        self.update_ui()

        if not ConfigManager.get_conf('general', 'hide_on_start'):
            self.show_all()
        self.paned_childs = []

    def init_ui(self):
        self.set_title(t('Terra Terminal Emulator'))

        if ConfigManager.get_conf(self.name, 'fullscreen'):
            self.is_fullscreen = True
        else:
            self.is_fullscreen = False

        self.slide_effect_running = False
        self.losefocus_time = 0
        self.set_has_resize_grip(False)

        self.main_container = self.builder.get_object('main_container')
        """:type: Gtk.Box"""
        self.main_container.reparent(self)

        self.logo = self.builder.get_object('logo')
        logo_path = os.path.join(TerraHandler.get_resources_path(), 'terra.svg')
        self.logo_buffer = GdkPixbuf.Pixbuf.new_from_file_at_size(logo_path, 32, 32)
        self.logo.set_from_pixbuf(self.logo_buffer)

        self.set_icon(self.logo_buffer)

        self.notebook = self.builder.get_object('notebook')
        self.notebook.set_name('notebook')

        self.tabbar = self.builder.get_object('tabbar')
        self.buttonbox = self.builder.get_object('buttonbox')

        # radio group leader, first and hidden object of buttonbox
        # keeps all other radio buttons in a group
        self.radio_group_leader = Gtk.RadioButton()
        self.buttonbox.pack_start(self.radio_group_leader, False, False, 0)
        self.radio_group_leader.set_no_show_all(True)

        self.new_page = self.builder.get_object('btn_new_page')
        self.new_page.connect('clicked', lambda w: self.add_page())

        self.btn_fullscreen = self.builder.get_object('btn_fullscreen')
        self.btn_fullscreen.connect('clicked', lambda w: self.toggle_fullscreen())

        self.connect('destroy', lambda w: self.quit())
        self.connect('delete-event', lambda w, x: self.quit())
        self.connect('key-press-event', self.on_keypress)
        self.connect('focus-out-event', self.on_window_losefocus)
        self.connect('configure-event', self.on_window_move)

        self.set_default_size(self.monitor.width, self.monitor.height)

        added = False
        for section in ConfigManager.get_sections():
            tabs = str('layout-Tabs-%d'% self.screen_id)
            if section.find(tabs) == 0 and not ConfigManager.get_conf(section, 'disabled'):
                self.add_page(page_name=str(section), update=False)
                added = True
        if not added:
            self.add_page(update=False)

        for button in self.buttonbox:
            if button == self.radio_group_leader:
                continue
            else:
                button.set_active(True)
                break

    def check_visible(self):
        if not terra_utils.is_on_visible_screen(self):
            active_monitor = self.screen.get_monitor_workarea(self.screen.get_primary_monitor())
            terra_utils.set_new_size(self, active_monitor, self.monitor)

    def on_window_losefocus(self, window, event):
        if self.slide_effect_running:
            return
        if ConfigManager.disable_losefocus_temporary:
            return
        if not ConfigManager.get_conf('window', 'hide_on_losefocus'):
            return

        if self.get_property('visible'):
            self.losefocus_time = GdkX11.x11_get_server_time(self.get_window())
            if ConfigManager.get_conf('window', 'use_animation'):
                self.slide_up()
            self.unrealize()
            self.hide()

    def on_window_move(self, window, event):
        if not self.is_fullscreen and event.x > 0 and event.y > 0 and self.get_visible() and \
           ((event.x != self.monitor.x and event.y != self.monitor.y) \
            or (event.width != self.monitor.width and event.height != self.monitor.height)):
            self.monitor.x = event.x
            self.monitor.y = event.y
            self.monitor.height = event.height
            self.monitor.width = event.width
            self.resize(self.monitor.width, self.monitor.height)
            self.set_default_size(self.monitor.width, self.monitor.height)
            self.show()

    def exit(self):
        if ConfigManager.get_conf('general', 'prompt_on_quit'):
            ConfigManager.disable_losefocus_temporary = True
            msgtext = t("Do you really want to quit?")
            msgbox = Gtk.MessageDialog(self, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, Gtk.ButtonsType.YES_NO, msgtext)
            response = msgbox.run()
            msgbox.destroy()
            ConfigManager.disable_losefocus_temporary = False

            if response != Gtk.ResponseType.YES:
                return False

        TerraHandler.Wins.app_quit()

    def save_conf(self, keep=True):
        tabs = str('layout-Tabs-%d' % self.screen_id)
        if not keep:
            # NOTE: Don't change the list while iterating over it.
            config_sections = ConfigManager.get_sections()
            for section in iter(config_sections):
                if section.find(tabs) == 0:
                    ConfigManager.del_conf(section)
            ConfigManager.del_conf(self.name)
        else:
            # We delete all tabs first to avoid unused.
            # We delete all layouts first to avoid unused.
            # NOTE: Don't change the list while iterating over it.
            config_sections = ConfigManager.get_sections()
            for section in iter(config_sections):
                if section.find('layout-Tabs-%d' % self.screen_id) == 0:
                    # We won't delete those who are set as disabled.
                    if not ConfigManager.get_conf(section, 'disabled'):
                        ConfigManager.del_conf(section)
                if section.find('layout-Child-%d' % self.screen_id) == 0:
                    ConfigManager.del_conf(section)

            ConfigManager.set_conf(self.name, 'width', self.monitor.width)
            ConfigManager.set_conf(self.name, 'height', self.monitor.height)
            ConfigManager.set_conf(self.name, 'posx', self.monitor.x)
            ConfigManager.set_conf(self.name, 'posy', self.monitor.y)
            ConfigManager.set_conf(self.name, 'fullscreen', self.is_fullscreen)

            # We add them all.
            tab_id = 0
            for button in self.buttonbox:
                if button != self.radio_group_leader:
                    section = str('layout-Tabs-%d-%d' % (self.screen_id, tab_id))
                    ConfigManager.set_conf(section, 'name', button.get_label())
                    tab_id += 1

            tab_id = 0
            for container in self.notebook.get_children():
                child_id = 0
                self.set_paned_parents(container)
                for child in terra_utils.my_sorted(container.vte_list):
                    section = str('layout-Child-%d-%d-%d' % (self.screen_id, tab_id, child_id))
                    print('Id: %d ParId: %d Pos: %d' % (child.id, child.parent, child.pos))
                    ConfigManager.set_conf(section, 'id', child.id)
                    ConfigManager.set_conf(section, 'parent', child.parent)
                    ConfigManager.set_conf(section, 'axis', child.axis)
                    ConfigManager.set_conf(section, 'pos', child.pos)
                    ConfigManager.set_conf(section, 'prog', child.progname)
                    ConfigManager.set_conf(section, 'pwd', child.pwd)
                    child_id += 1
                tab_id += 1

    def use_child(self, child, parent, axis, pos):
        child.pos = -1
        child.axis = axis
        child.pwd = terra_utils.get_pwd(child.pid[1])
        if parent:
            child.pos = pos
            child.parent = parent.id

    # There is a very small issue if the tabbar is visible.
    def get_paned_pos(self, tree):
        pos = tree.get_position()
        if isinstance(tree, Gtk.HPaned):
            size = tree.get_allocation().width
        else:
            size = tree.get_allocation().height
        percentage = int(float(pos) / float(size) * float(10000))
        return percentage

    def rec_parents(self, tree, container):
        if not tree:
            TerminalWin.rec_parents.im_func._parent = None
            TerminalWin.rec_parents.im_func._first_child = None
            TerminalWin.rec_parents.im_func._axis = 'v'
            TerminalWin.rec_parents.im_func._pos = -1
            return None

        if isinstance(tree, Gtk.Paned):
            child1 = tree.get_child1()
            child2 = tree.get_child2()
            if child1:
                if isinstance(child1, Gtk.Paned):
                    TerminalWin.rec_parents.im_func._pos = self.get_paned_pos(tree)
                    self.rec_parents(child1, container)
                if isinstance(child1, VteObject):
                    if not terra_utils.get_paned_parent(container.vte_list, child1.parent):
                        self.use_child(child1, TerminalWin.rec_parents.im_func._parent, TerminalWin.rec_parents.im_func._axis, TerminalWin.rec_parents.im_func._pos)
                    else:
                        self.use_child(child1, terra_utils.get_paned_parent(container.vte_list, child1.parent), TerminalWin.rec_parents.im_func._axis, TerminalWin.rec_parents.im_func._pos)
                    if not TerminalWin.rec_parents.im_func._first_child:
                        if child1 in container.vte_list:
                            container.vte_list.remove(child1)
                        if len(container.vte_list) and container.vte_list[0].id == 0:
                            container.vte_list.pop(0)
                        for item in container.vte_list:
                            if item.parent == child1.id:
                                item.parent = 0
                        child1.id = 0
                        child1.parent = 0
                        container.vte_list.append(child1)
                        TerminalWin.rec_parents.im_func._first_child = child1
                    TerminalWin.rec_parents.im_func._parent = child1
            if child2:
                if isinstance(tree, Gtk.HPaned):
                    TerminalWin.rec_parents.im_func._axis = 'h'
                else:
                    TerminalWin.rec_parents.im_func._axis = 'v'
                if isinstance(child2, Gtk.Paned):
                    TerminalWin.rec_parents.im_func._pos = self.get_paned_pos(tree)
                    self.rec_parents(child2, container)
                if isinstance(child2, VteObject):
                    if not terra_utils.get_paned_parent(container.vte_list, child2.parent):
                        self.use_child(child2, TerminalWin.rec_parents.im_func._parent, TerminalWin.rec_parents.im_func._axis, self.get_paned_pos(tree))
                    else:
                        self.use_child(child2, terra_utils.get_paned_parent(container.vte_list, child2.parent), TerminalWin.rec_parents.im_func._axis, self.get_paned_pos(tree))

        elif not TerminalWin.rec_parents.im_func._first_child and isinstance(tree, VteObject):
            if tree in container.vte_list:
                container.vte_list.remove(tree)
            if len(container.vte_list) and container.vte_list[0].id == 0:
                container.vte_list.pop(0)
            tree.id = 0
            tree.parent = 0
            tree.pos = -1
            tree.axis = 'v'
            container.vte_list.append(tree)
            TerminalWin.rec_parents.im_func._first_child = tree

    def set_paned_parents(self, container):
        self.rec_parents(None, None)
        for tree in container.get_children():
            self.rec_parents(tree, container)

    def quit(self):
        TerraHandler.remove_ui_event_handler(self.update_ui)
        TerraHandler.Wins.remove_app(self)
        self.destroy()

    def add_page(self, page_name=None, update=True):
        container = None
        if page_name:
            section = str('layout-Child-%s-0' % (page_name[len('layout-Tabs-'):]))
            progname = ConfigManager.get_conf(section, 'prog')
            pwd = ConfigManager.get_conf(section, 'pwd')
            container = VteObjectContainer(self, progname=progname, pwd=pwd)
        if not container:
            container = VteObjectContainer(self)

        self.notebook.append_page(container, None)
        self.notebook.set_current_page(-1)
        self.get_active_terminal().grab_focus()

        page_count = 0
        for button in self.buttonbox:
            if button != self.radio_group_leader:
                page_count += 1

        if page_name is not None:
            tab_name = ConfigManager.get_conf(page_name, 'name')
        if page_name is None or tab_name is None:
            tab_name = t("Terminal ") + str(page_count + 1)

        new_button = Gtk.RadioButton.new_with_label_from_widget(self.radio_group_leader, tab_name)
        new_button.set_property('draw-indicator', False)
        new_button.set_active(True)
        new_button.show()
        new_button.connect('toggled', self.change_page)
        new_button.connect('button-release-event', self.page_button_mouse_event)

        self.buttonbox.pack_start(new_button, False, True, 0)

        if page_name:
            for section in ConfigManager.get_sections():
                child = str('layout-Child-%s'%(page_name[len('layout-Tabs-'):]))
                if section.find(child) == 0 and section[-1:] != '0':
                    axis = ConfigManager.get_conf(section, "axis")[0]
                    prog = ConfigManager.get_conf(section, "prog")
                    pos = ConfigManager.get_conf(section, "pos")
                    pwd = ConfigManager.get_conf(section, "pwd")
                    term_id = int(ConfigManager.get_conf(section, "id"))
                    parent_vte = terra_utils.get_paned_parent(container.vte_list, int(ConfigManager.get_conf(section, "parent")))
                    if parent_vte:
                        parent_vte.split_axis(parent_vte, axis=axis, split=pos, progname=prog, term_id=term_id, pwd=pwd)
                    else:
                        print("DEBUG: no parent(%d) found for section: %s"% (int(ConfigManager.get_conf(section, "parent")), section))
        if update:
            self.update_ui()

    def get_active_terminal(self):
        return self.notebook.get_nth_page(self.notebook.get_current_page()).active_terminal

    def change_page(self, button):
        if not button.get_active():
            return

        page_no = 0
        for i in self.buttonbox:
            if i != self.radio_group_leader:
                if i == button:
                    self.notebook.set_current_page(page_no)
                    self.get_active_terminal().grab_focus()
                    return
                page_no += 1

    def page_button_mouse_event(self, button, event):
        if event.button != 3:
            return

        self.menu = self.builder.get_object('page_button_menu')
        self.menu.connect('deactivate', lambda w: setattr(ConfigManager, 'disable_losefocus_temporary', False))

        self.menu_close = self.builder.get_object('menu_close')
        self.menu_rename = self.builder.get_object('menu_rename')

        try:
            self.menu_rename.disconnect(self.menu_rename_signal)
            self.menu_close.disconnect(self.menu_close_signal)

            self.menu_close_signal = self.menu_close.connect('activate', self.page_close, button)
            self.menu_rename_signal = self.menu_rename.connect('activate', self.page_rename, button)
        except:
            self.menu_close_signal = self.menu_close.connect('activate', self.page_close, button)
            self.menu_rename_signal = self.menu_rename.connect('activate', self.page_rename, button)

        self.menu.show_all()

        ConfigManager.disable_losefocus_temporary = True
        self.menu.popup(None, None, None, None, event.button, event.time)
        self.get_active_terminal().grab_focus()

    def page_rename(self, menu, sender):
        current_tab_name = sender.get_label()

        dialog = InputDialog(
            parent=self.get_toplevel(),
            title=t('Rename Tab'),
            label=t('New tab name:'),
            entry_text=current_tab_name,
        )
        response = dialog.run()

        if response == Gtk.ResponseType.APPLY:
            new_tab_name = dialog.get_entry_text()

            if new_tab_name:
                sender.set_label(new_tab_name)

        dialog.destroy()

    def page_close(self, menu, sender):
        button_count = len(self.buttonbox.get_children())

        # don't forget "radio_group_leader"
        if button_count <= 2:
            if ConfigManager.get_conf('general', 'spawn_term_on_last_close'):
                self.add_page()
            else:
                return self.quit()

        page_no = 0
        for i in self.buttonbox:
            if i != self.radio_group_leader:
                if i == sender:
                    self.notebook.remove_page(page_no)
                    self.buttonbox.remove(i)

                    last_button = self.buttonbox.get_children()[-1]
                    last_button.set_active(True)
                    return True
                page_no += 1

    def get_screen_rectangle(self):
        display = self.screen.get_display()
        return self.screen.get_monitor_workarea(self.screen.get_monitor_at_point(self.monitor.x, self.monitor.y))

    # @TODO: Cleanup!
    def update_ui(self):
        self.unmaximize()
        self.stick()
        self.override_gtk_theme()
        self.set_keep_above(ConfigManager.get_conf('window', 'always_on_top'))
        self.set_decorated(ConfigManager.get_conf('window', 'use_border'))
        self.set_skip_taskbar_hint(ConfigManager.get_conf('general', 'hide_from_taskbar'))

        # hide/show tabbar.
        if ConfigManager.get_conf(self.name, 'hide-tab-bar'):
            self.tabbar.hide()
            self.tabbar.set_no_show_all(True)
        else:
            self.tabbar.set_no_show_all(False)
            self.tabbar.show()

        self.check_visible()

        if self.is_fullscreen:
            win_rect = self.get_screen_rectangle()
            self.reshow_with_initial_size()
            self.move(win_rect.x, win_rect.y)
            self.fullscreen()

            # hide tab bar
            if ConfigManager.get_conf(self.name, 'hide-tab-bar-fullscreen'):
                self.tabbar.set_no_show_all(True)
                self.tabbar.hide()
        else:
            vertical_position = self.monitor.y
            horizontal_position = self.monitor.x
            screen_rectangle = self.get_screen_rectangle()
            vert = ConfigManager.get_conf(self.name, 'vertical-position')
            if vert is not None and vert <= 100:
                height = self.monitor.height
                vertical_position = vert * screen_rectangle.height / 100
                # top
                if vertical_position - (height / 2) < 0:
                    vertical_position = screen_rectangle.y + 0
                # bottom
                elif vertical_position + (height / 2) > screen_rectangle.height:
                    vertical_position = screen_rectangle.y + screen_rectangle.height - height
                # center
                else:
                    vertical_position = screen_rectangle.y + vertical_position - (height / 2)

            horiz = ConfigManager.get_conf(self.name, 'horizontal-position')
            if horiz is not None and horiz <= 100:
                width = self.monitor.width - 1
                horizontal_position = horiz * screen_rectangle.width / 100
                # left
                if horizontal_position - (width / 2) < 0:
                    horizontal_position = screen_rectangle.x + 0
                # right
                elif horizontal_position + (width / 2) > screen_rectangle.width:
                    horizontal_position = screen_rectangle.x + screen_rectangle.width - width
                # center
                else:
                    horizontal_position = screen_rectangle.x + horizontal_position - (width / 2)
            self.unfullscreen()
            self.reshow_with_initial_size()
            self.move(horizontal_position, vertical_position)

    def override_gtk_theme(self):
        css_provider = Gtk.CssProvider()

        bg = Gdk.color_parse(ConfigManager.get_conf('terminal', 'color_background'))
        bg_hex = '#%02X%02X%02X' % (
            int((bg.red / 65536.0) * 256),
            int((bg.green / 65536.0) * 256),
            int((bg.blue / 65536.0) * 256)
        )

        separator_size = ConfigManager.get_conf('general', 'separator_size')
        css_provider.load_from_data('''
            #notebook GtkPaned {
                -GtkPaned-handle-size: %i;
            }
            GtkVScrollbar {
                -GtkRange-slider-width: 5;
            }
            GtkVScrollbar.trough {
                background-image: none;
                background-color: %s;
                border-width: 0;
                border-radius: 0;
            }
            GtkVScrollbar.slider, GtkVScrollbar.slider:prelight, GtkVScrollbar.button {
                background-image: none;
                border-width: 0;
                background-color: alpha(#FFF, 0.4);
                border-radius: 10px;
                box-shadow: none;
            }
            ''' % (int(separator_size), bg_hex))

        style_context = Gtk.StyleContext()
        style_context.add_provider_for_screen(self.screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def on_keypress(self, widget, event):
        if self.key_event_compare('toggle_scrollbars_key', event):
            # Toggle value
            ConfigManager.set_conf('terminal', 'show_scrollbar', not ConfigManager.get_conf('terminal', 'show_scrollbar'))
            TerraHandler.execute_ui_event_handlers()
            return True

        if self.key_event_compare('move_up_key', event):
            self.get_active_terminal().move(direction=1)
            return True

        if self.key_event_compare('move_down_key', event):
            self.get_active_terminal().move(direction=2)
            return True

        if self.key_event_compare('move_left_key', event):
            self.get_active_terminal().move(direction=3)
            return True

        if self.key_event_compare('move_right_key', event):
            self.get_active_terminal().move(direction=4)
            return True

        if self.key_event_compare('move_left_screen_key', event):
            terra_utils.move_left_screen(self)
            return True

        if self.key_event_compare('move_right_screen_key', event):
            terra_utils.move_right_screen(self)
            return True

        if self.key_event_compare('quit_key', event):
            self.quit()
            return True

        if self.key_event_compare('select_all_key', event):
            self.get_active_terminal().select_all()
            return True

        if self.key_event_compare('copy_key', event):
            self.get_active_terminal().copy_clipboard()
            return True

        if self.key_event_compare('paste_key', event):
            self.get_active_terminal().paste_clipboard()
            return True

        if self.key_event_compare('split_v_key', event):
            self.get_active_terminal().split_axis(None, 'h')
            return True

        if self.key_event_compare('split_h_key', event):
            self.get_active_terminal().split_axis(None, 'v')
            return True

        if self.key_event_compare('close_node_key', event):
            self.get_active_terminal().close_node(None)
            return True

        if self.key_event_compare('fullscreen_key', event):
            self.toggle_fullscreen()
            return True

        if self.key_event_compare('new_page_key', event):
            self.add_page()
            return True

        if self.key_event_compare('rename_page_key', event):
            for button in self.buttonbox:
                if button != self.radio_group_leader and button.get_active():
                    self.page_rename(None, button)
                    return True

        if self.key_event_compare('close_page_key', event):
            for button in self.buttonbox:
                if button != self.radio_group_leader and button.get_active():
                    self.page_close(None, button)
                    return True

        if self.key_event_compare('next_page_key', event):
            page_button_list = self.buttonbox.get_children()[1:]

            for i in range(len(page_button_list)):
                if page_button_list[i].get_active():
                    if (i + 1) < len(page_button_list):
                        page_button_list[i+1].set_active(True)
                    else:
                        page_button_list[0].set_active(True)
                    return True

        if self.key_event_compare('prev_page_key', event):
            page_button_list = self.buttonbox.get_children()[1:]

            for i in range(len(page_button_list)):
                if page_button_list[i].get_active():
                    if i > 0:
                        page_button_list[i-1].set_active(True)
                    else:
                        page_button_list[-1].set_active(True)
                    return True

        if self.key_event_compare('move_page_left_key', event):
            i = 0
            for button in self.buttonbox:
                if button != self.radio_group_leader and button.get_active():
                    if (i - 1) > 0:
                        self.notebook.reorder_child(self.notebook.get_nth_page(i - 1), i - 2)
                        self.buttonbox.reorder_child(button, i - 1)
                        return True
                    else:
                        return False
                i += 1

        if self.key_event_compare('move_page_right_key', event):
            i = 0
            for button in self.buttonbox:
                if button != self.radio_group_leader and button.get_active():
                    if (i + 1) < len(self.buttonbox):
                        self.notebook.reorder_child(self.notebook.get_nth_page(i - 1), i)
                        self.buttonbox.reorder_child(button, i + 1)
                        return True
                    else:
                        return False
                i += 1

    @staticmethod
    def key_event_compare(conf_name, event):
        key_string = ConfigManager.get_conf('shortcuts', conf_name)

        if ((Gdk.ModifierType.CONTROL_MASK & event.state) == Gdk.ModifierType.CONTROL_MASK) != ('<Control>' in key_string):
            return False

        if ((Gdk.ModifierType.MOD1_MASK & event.state) == Gdk.ModifierType.MOD1_MASK) != ('<Alt>' in key_string):
            return False

        if ((Gdk.ModifierType.SHIFT_MASK & event.state) == Gdk.ModifierType.SHIFT_MASK) != ('<Shift>' in key_string):
            return False

        if ((Gdk.ModifierType.SUPER_MASK & event.state) == Gdk.ModifierType.SUPER_MASK) != ('<Super>' in key_string):
            return False

        key_string = key_string.replace('<Control>', '')
        key_string = key_string.replace('<Alt>', '')
        key_string = key_string.replace('<Shift>', '')
        key_string = key_string.replace('<Super>', '')

        if key_string.lower() != Gdk.keyval_name(event.keyval).lower():
            return False

        return True

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.update_ui()

    def init_transparency(self):
        self.set_app_paintable(True)
        visual = self.screen.get_rgba_visual()
        if visual is not None and self.screen.is_composited():
            self.set_visual(visual)
        else:
            ConfigManager.use_fake_transparency = True

    def update_events(self):
        while Gtk.events_pending():
            Gtk.main_iteration()
        Gdk.flush()

    def slide_up(self, i=0):
        self.slide_effect_running = True
        step = ConfigManager.get_conf('window', 'animation_step_count')
        if not self.is_fullscreen:
            win_rect = self.monitor
        else:
            win_rect = self.get_allocation()
        if self.get_window() is not None:
            self.get_window().enable_synchronized_configure()
        if i < (step + 1):
            self.resize(win_rect.width, win_rect.height - int(((win_rect.height/step) * i)))
            self.queue_resize()
            self.update_events()
            GObject.timeout_add(ConfigManager.get_conf('window', 'animation_step_time'), self.slide_up, i+1)
        else:
            self.hide()
            self.unrealize()
        if self.get_window() is not None:
            self.get_window().configure_finished()
        self.slide_effect_running = False

    def slide_down(self, i=1):
        self.slide_effect_running = True
        step = ConfigManager.get_conf('window', 'animation_step_count')
        if not self.is_fullscreen:
            win_rect = self.monitor
        else:
            win_rect = self.get_screen_rectangle()
        if self.get_window() is not None:
            self.get_window().enable_synchronized_configure()
        if i < (step + 1):
            self.resize(win_rect.width, int(((win_rect.height/step) * i)))
            self.queue_resize()
            self.update_events()
            GObject.timeout_add(ConfigManager.get_conf('window', 'animation_step_time'), self.slide_down, i+1)
        if self.get_window() is not None:
            self.get_window().configure_finished()
        self.slide_effect_running = False

    def show_hide(self):
        if self.slide_effect_running:
            return
        event_time = self.hotkey.get_current_event_time()
        if self.losefocus_time and self.losefocus_time >= event_time:
            return

        if self.get_visible():
            if ConfigManager.get_conf('window', 'use_animation'):
                self.slide_up()
            else:
                self.hide()
            return
        else:
            if ConfigManager.get_conf('window', 'use_animation'):
                self.slide_down()
            self.update_ui()
            self.show()
