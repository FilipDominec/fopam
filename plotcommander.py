#!/usr/bin/python3
#-*- coding: utf-8 -*-

import gi, sys, os, signal, stat, traceback
import numpy as np

## Plotting dependencies and settings
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository.GdkPixbuf import Pixbuf,Colorspace

import matplotlib
from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo  as FigureCanvas # "..Agg" backend is broken currently
from matplotlib.backends.backend_gtk3      import NavigationToolbar2GTK3 as NavigationToolbar


## TODO These settings should be loaded dynamically from ./plotcommanderrc.py, ../plotcommanderrc.py, ../../plotcommanderrc.py, ...
matplotlib.rcParams['font.family'] = 'serif'        
matplotlib.rcParams['font.size'] = 9
matplotlib.rcParams['axes.linewidth'] = .5
matplotlib.rcParams['savefig.facecolor'] = "white"
#import FDMeasurementRecords

class Handler:
    ## == initialization == 
    def __init__(self): #{{{
        self.lockTreeViewEvents = False
        np.seterr(all='ignore')

        ## Plotting initialization
        self.fig = matplotlib.figure.Figure(figsize=(8,8), dpi=96, facecolor='#eeeeee', tight_layout=1)
        self.ax = self.fig.add_subplot(111) 
        self.canvas = FigureCanvas(self.fig)
        self.canvas.set_size_request(300,300)
        self.toolbar = matplotlib.backends.backend_gtk3.NavigationToolbar2GTK3(self.canvas, w('box4').get_parent_window())
        self.sw = Gtk.ScrolledWindow()
        self.sw.add_with_viewport(self.canvas)
        w('box4').pack_start(self.toolbar, False, True, 0)
        #self.toolbar.append_item(Gtk.Button('tetet')) 
        ## TODO find out how to modify the NavigationToolbar...
        w('box4').pack_start(self.sw, True, True, 0)
        self.toolbar.pan() 
        #TODO - define global shortcuts as a superset of the Matplotlib-GUI's internal, include also:
        #toolbar.zoom() #toolbar.home() #toolbar.back() #toolbar.forward() #toolbar.save_figure(toolbar)
        #TODO http://stackoverflow.com/questions/26433169/personalize-matplotlib-toolbar-with-log-feature
        #TODO http://dalelane.co.uk/blog/?p=778


        ## TreeStore and ListStore initialization
        self.tsFiles = Gtk.TreeStore(str,        Pixbuf, str,        Pixbuf        )
        ## column meaning:              0:filepath  1:icon  2:name      3:plotstyleicon
        self.dummy_treestore_row = [None, None, None, None]

        treeViewCol0 = Gtk.TreeViewColumn("Plot")        # Create a TreeViewColumn
        colCellPlot = Gtk.CellRendererPixbuf()        # Create a column cell to display text
        treeViewCol0.pack_start(colCellPlot, expand=True)
        treeViewCol0.add_attribute(colCellPlot, "pixbuf", 3)    # set params for icon
        w('treeview1').append_column(treeViewCol0)       # Append the columns to the TreeView

        treeViewCol = Gtk.TreeViewColumn("File")        # Create a TreeViewColumn
        colCellImg = Gtk.CellRendererPixbuf()       # Create a column cell to display an image
        colCellText = Gtk.CellRendererText()        # Create a column cell to display text
        treeViewCol.pack_start(colCellImg, expand=False)       # Add the cells to the column
        treeViewCol.pack_start(colCellText, expand=True)
        treeViewCol.add_attribute(colCellImg, "pixbuf", 1)      # Bind the image cell to column 1 of the tree's model
        treeViewCol.add_attribute(colCellText, "text", 2)       # Bind the text cell to column 0 of the tree's model
        w('treeview1').append_column(treeViewCol)       # Append the columns to the TreeView
        w('treeview1').set_expander_column(treeViewCol)

        w('treeview1').set_model(self.tsFiles)       # Append the columns to the TreeView
        w('treeview1').set_enable_tree_lines(True) 
        w('treeview1').connect("row-expanded", self.onRowExpanded)       # add "on expand" callback
        w('treeview1').connect("row-collapsed", self.onRowCollapsed)         # add "on collapse" callback
        w('treeview1').get_selection().set_select_function(self.treeview1_selectmethod, data=None) # , full=True

        ## TODO: If files are specified as arguments, select these at start, and plot them at once

        ## If a directory is specified, just set it as the root of the file list. If none, use current working dir.
        self.treeViewRootDir = os.getcwd() if len(sys.argv)<=1  else  sys.argv[1]
        self.populateFileSystemTreeStore(self.tsFiles, basepath=self.treeViewRootDir, parent=None, include_up_dir=True)
        self.plot_reset()
        self.plot_all_sel_records()


        ## Add the data cursor by default  # TODO - make this work
        from matplotlib.widgets import Cursor
        cursor = Cursor(self.ax, useblit=True, color='red', linewidth=2)

        #}}}
    ## === FILE HANDLING ===
    def populateFileSystemTreeStore(self, treeStore, basepath, parent=None, include_up_dir=False):
        ## If we update the whole tree, it has to be cleared first. 
        ## During this operation, its selection will change, but the plots should not be updated so that it is fast.

        if parent == None:
            ## Clear all rows including their icons
            self.lockTreeViewEvents = True
            self.tsFiles.clear()
            self.lockTreeViewEvents = False

        def recursive_clear_icon(treeIter):
            while treeIter != None: 
                iterpixbuf = self.tsFiles.get_value(treeIter, 3)
                if iterpixbuf: iterpixbuf.fill(self.array2rgbhex([.5,.5,1], alpha=0)) ## some nodes may have pixbuf set to None
                recursive_clear_icon(self.tsFiles.iter_children(treeIter))
                treeIter=self.tsFiles.iter_next(treeIter)
        recursive_clear_icon(self.tsFiles.get_iter_first())

        itemCounter = 0
        if include_up_dir:
            itemIcon = Gtk.IconTheme.get_default().load_icon('go-up', 8, 0) # Generate a default icon
            plotstyleIcon = Pixbuf.new(Colorspace.RGB, True, 8, 10, 10)
            plotstyleIcon.fill(0xffffffff)
            currentIter = treeStore.append(parent, [basepath, itemIcon, '..', plotstyleIcon])  # Append the item to the TreeStore
            treeStore.append(currentIter, self.dummy_treestore_row)

        itemFullNames = [os.path.join(basepath,filename) for filename in os.listdir(basepath)]
        itemFullNames.sort()
        def is_folder(itemFullName): ## Shorthand
            return stat.S_ISDIR(os.stat(itemFullName).st_mode) # Extract metadata from the item
        itemFullNames = [f for f in itemFullNames if is_folder(f)] + [f for f in itemFullNames if not is_folder(f)]   # folders above files


        fileFilterString = w('enFileFilter').get_text().strip()
        for itemFullName in itemFullNames:
            if is_folder(itemFullName):                       
                icon = 'folder'
            elif self.guess_file_type(itemFullName) == 'unknown':   
                icon = 'gtk-stop' 
            else:                                               
                icon = 'empty'

            ## If specified, apply filter to files (but not directories)
            if fileFilterString=="" or (fileFilterString in os.path.basename(itemFullName)) or is_folder(itemFullName):
                itemIcon = Gtk.IconTheme.get_default().load_icon(icon, 8, 0) # Generate a default icon
                plotstyleIcon = Pixbuf.new(Colorspace.RGB, True, 8, 10, 10)
                plotstyleIcon.fill(0xffffffff)
                currentIter = treeStore.append(parent, 
                        [itemFullName, itemIcon, os.path.basename(itemFullName), plotstyleIcon])  # Append the item to the TreeStore

            if is_folder(itemFullName): 
                treeStore.append(currentIter, self.dummy_treestore_row)      # add dummy if current item was a folder

            itemCounter += 1                                    #increment the item counter
        if itemCounter < 1: treeStore.append(parent, self.dummy_treestore_row)        # add the dummy node back if nothing was inserted before
    ## === GRAPHICAL PRESENTATION ===
    def array2rgbhex(self,arr3,alpha=1): # {{{
        return  int(arr3[0]*256-.5)*(256**3) +\
                int(arr3[1]*256-.5)*(256**2) +\
                int(arr3[2]*256-.5)*(256**1) +\
                int(alpha*255  -.5)
# }}}
    def plot_reset(self):# {{{
        self.ax.cla() ## TODO clearing matplotlib plot - this is inefficient, rewrite

        def recursive_clear_icon(treeIter):
            while treeIter != None: 
                iterpixbuf = self.tsFiles.get_value(treeIter, 3)
                if iterpixbuf: iterpixbuf.fill(self.array2rgbhex([.5,.5,1], alpha=0)) ## some nodes may have pixbuf set to None
                recursive_clear_icon(self.tsFiles.iter_children(treeIter))
                treeIter=self.tsFiles.iter_next(treeIter)
        recursive_clear_icon(self.tsFiles.get_iter_first())
        w('treeview1').queue_draw()
# }}}
    def plot_all_sel_records(self):# {{{
        (model, pathlist) = w('treeview1').get_selection().get_selected_rows()
        if len(pathlist) == 0: return

        ## Generate the color palette
        #color_palette = ["g"]*len(pathlist) ## TODO use some real palette
        color_pre_map = np.linspace(0.05, .95, len(pathlist)+1)[:-1]
        color_palette = matplotlib.cm.gist_rainbow(color_pre_map*.5 + np.sin(color_pre_map*np.pi/2)**2*.5)

        ## Plot all curves sequentially
        error_counter = 0
        for (path, color_from_palette) in zip(pathlist, color_palette):
            try:
                ## Plot the line first
                file_name = self.tsFiles.get_value(self.tsFiles.get_iter(path), 0)
                self.plot_record(file_name, plot_style={'color':color_from_palette})

                ## If no exception occurs, colour the icon according to the line colour
                self.tsFiles.get_value(self.tsFiles.get_iter(path), 3).fill(self.array2rgbhex(color_from_palette))

            except ValueError:
                traceback.print_exc()
                error_counter += 1
        #self.ax.legend(loc="auto")
        self.ax.grid(True)
        w('statusbar1').push(0,"During last file-selection operation, %d errors were encountered" % error_counter)
# }}}
    ## == FILE AND DATA UTILITIES ==
    def guess_file_type(self, infile):# {{{
        if   infile[-4:].lower() in ('.csv', '.dat',):
            return 'csv'
        elif infile[-4:].lower() in ('.xls'):
            return 'xls'
        elif infile[-4:].lower() in ('.opj'):       
            return 'opj'
        else:
            return 'unknown'
# }}}
    def safe_to_float(self, x_raw, y_raw, x0=[], y0=[]):# {{{
        
        # safe simultaneous conversion of both data columns; error in either value leads to skipped row
        for x_raw, y_raw in zip(x_raw,y_raw): 
            try: x1, y1 = float(x_raw), float(y_raw); x0.append(x1); y0.append(y1)
            except: pass
        return np.array(x0),  np.array(y0)
# }}}
    def plot_record(self, infile, plot_style={}, xcolumn=0, ycolumn=1):# {{{
        ## Plotting "on-the-fly", i.e., program does not store any data and loads them from disk upon every (re)plot

        import pandas as pd
        if   self.guess_file_type(infile) == 'opj':
            return ## NOTE: support for liborigin not tested yet! 
        elif self.guess_file_type(infile) == 'xls':
            xl = pd.ExcelFile(infile, header=1) ##  
            ## TODO: print(xl.sheet_names)    a XLS file is a *container* with multiple sheets, a sheet may contain multiple columns
            df = xl.parse() 
            x,y = df.values.T[xcolumn], df.values.T[ycolumn] ## TODO Should offer choice of columns
        else:             ## for all remaining filetypes, try to interpret as a text table
            from io import StringIO ## this is just a hack to avoid loading different comment lines
            output = StringIO(); output.writelines(line for line in open(infile) if line[:1] not in "!;,%"); output.seek(0)
            df = pd.read_csv(output, comment='#', delim_whitespace=True, error_bad_lines=False) 
            ## sep=None     -- automatic detection of separators clashes with delim_whitespace=True, error_bad_lines=False
            output.close()
            #x, y = df[xcolumn], df[ycolumn] ## TODO: selection of columns!
            x, y = df.values.T[0], df.values.T[1] ## TODO: selection of columns!

        try:                    ## if possible, use also the first row as numeric data
            #print (df.columns)
            x, y = self.safe_to_float(x, y, x0=[float(df.columns[xcolumn])], y0=[float(df.columns[ycolumn])])
            xlabel, ylabel = "x", "y"
        except ValueError:      ## if conversion fails, use the first row as column names instead
            x, y = self.safe_to_float(x, y, x0=[], y0=[])
            xlabel, ylabel = df.columns[xcolumn], df.columns[ycolumn]
        self.ax.plot(x, y, label=os.path.basename(infile), **plot_style) # TODO apply plotting options
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        #except:
            #pass
# }}}
    ## == USER INTERFACE HANDLERS ==
    def treeview1_selectmethod(self, selection, model, treePath, is_selected, user_data):# {{{
        ## Expand a directory by clicking, but do not allow user to select it
        treeiter        = self.tsFiles.get_iter(treePath)
        filenamepath    = self.tsFiles.get_value(treeiter, 0)
        if not filenamepath: return False
        itemMetaData    = os.stat(filenamepath) 
        itemIsFolder    = stat.S_ISDIR(itemMetaData.st_mode) # Extract metadata from the item

        selected_row_names = self.remember_treeView_selected_rows(self.tsFiles, w('treeview1'))
        if itemIsFolder: ### TODO allow expanding multi-column files, too
            if w('treeview1').row_expanded(treePath):
                w('treeview1').collapse_row(treePath)
            else:
                w('treeview1').expand_row(treePath, open_all=False)
            print(selected_row_names)
            self.restore_treeView_selected_rows(selected_row_names)
            return False
        else:
            return True
# }}}
    def on_enFileFilter_activate(self, *args):# {{{
        expanded_row_names = self.remember_treeView_expanded_rows(self.tsFiles, w('treeview1'))    
        selected_row_names = self.remember_treeView_selected_rows(self.tsFiles, w('treeview1'))
        # Passing parent=None will populate the whole tree again
        #self.lockTreeViewEvents = True
        self.populateFileSystemTreeStore(self.tsFiles, basepath=self.treeViewRootDir, parent=None, include_up_dir=True)       
        #self.lockTreeViewEvents = False
        self.restore_treeView_expanded_rows(expanded_row_names)
        self.restore_treeView_selected_rows(selected_row_names)
        # }}}
    def remember_treeView_expanded_rows(self, treeStore, treeView):    # {{{
        ## returns a list of paths of expanded files/directories
        expanded_row_names = []
        def remember_treeview_states(treeIter):
            while treeIter != None: 
                if w('treeview1').row_expanded(treeStore.get_path(treeIter)):
                    expanded_row_names.append(treeStore.get_value(treeIter, 0))      # get the full path of the position
                remember_treeview_states(treeStore.iter_children(treeIter))
                treeIter=treeStore.iter_next(treeIter)
        remember_treeview_states(treeStore.get_iter_first())
        print("remember_treeView_expanded_rows: expanded_row_names", expanded_row_names)
        return expanded_row_names
        # }}}
    def remember_treeView_selected_rows(self, treeStore, treeView):# {{{
        ## returns a list of paths of selected files/directories
        (model, selectedPathList) = treeView.get_selection().get_selected_rows()
        selected_row_names = []
        for treePath in selectedPathList:
            selected_row_names.append(treeStore.get_value(treeStore.get_iter(treePath), 0))
        return selected_row_names
        # }}}
    def restore_treeView_expanded_rows(self, expanded_row_names):# {{{
        def recursive_expand_rows(treeIter, ):
            while treeIter != None: 
                if self.tsFiles.get_value(treeIter, 0) in expanded_row_names:
                    self.lockTreeViewEvents = True
                    w('treeview1').expand_row(self.tsFiles.get_path(treeIter), open_all=False)
                    self.lockTreeViewEvents = False
                recursive_expand_rows(self.tsFiles.iter_children(treeIter))
                treeIter=self.tsFiles.iter_next(treeIter)
        recursive_expand_rows(self.tsFiles.get_iter_first())
        # }}}
    def restore_treeView_selected_rows(self, selected_row_names):# {{{
        def recursive_select_rows(treeIter):
            while treeIter != None: 
                if self.tsFiles.get_value(treeIter, 0) in selected_row_names:
                    w('treeview1').get_selection().select_path(self.tsFiles.get_path(treeIter))
                recursive_select_rows(self.tsFiles.iter_children(treeIter))
                treeIter=self.tsFiles.iter_next(treeIter)
        recursive_select_rows(self.tsFiles.get_iter_first())
        self.plot_all_sel_records()
        # }}}
    def on_enFileFilter_focus_out_event(self, *args):# {{{
        self.on_enFileFilter_activate(self)
    # }}}
    def on_enColFilter_activate(self, *args):# {{{ TODO
        pass
    def on_enColFilter_focus_out_event(self, *args):
        pass
# }}}
    def onRowExpanded(self, treeView, treeIter, treePath):# {{{
        if self.lockTreeViewEvents: return      ## prevent event handlers triggering other events
        newPath = self.tsFiles.get_value(treeIter, 0)      # get the full path of the position
        if self.tsFiles.get_value(treeIter, 2) == "..":  ## if the expanded row was "..", change to up-dir
            expanded_row_names = self.remember_treeView_expanded_rows(self.tsFiles, w('treeview1'))    
            selected_row_names = self.remember_treeView_selected_rows(self.tsFiles, w('treeview1'))
            self.populateFileSystemTreeStore(self.tsFiles, basepath=os.path.dirname(self.treeViewRootDir), 
                    parent=None, include_up_dir=True)       
            self.restore_treeView_expanded_rows(expanded_row_names)
            self.restore_treeView_selected_rows(selected_row_names)
        else:
            self.populateFileSystemTreeStore(self.tsFiles, newPath, treeIter)       # populate the subtree on curent position
            self.tsFiles.remove(self.tsFiles.iter_children(treeIter))         # remove the first child (dummy node)
    # }}}
    def onRowCollapsed(self, treeView, treeIter, treePath):# {{{ 
        ## Remove all child nodes of the given row to free memory
        if self.lockTreeViewEvents: return      ## prevent event handlers triggering other events
        currentChildIter = self.tsFiles.iter_children(treeIter)
        while currentChildIter:         
            self.tsFiles.remove(currentChildIter)
            currentChildIter = self.tsFiles.iter_children(treeIter)
        self.tsFiles.append(treeIter, self.dummy_treestore_row)
    # }}}
    def on_treeview1_selection_changed(self, *args):# {{{       ## triggers replot
        if self.lockTreeViewEvents: return      ## prevent event handlers triggering other events
        self.plot_reset()               ## first delete the curves, to hide (also) unselected plots
        self.plot_all_sel_records()     ## then show the selected ones
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()
    # }}}
    def on_window1_delete_event(self, *args):# {{{
        Gtk.main_quit(*args)# }}}

signal.signal(signal.SIGINT, signal.SIG_DFL)
builder = Gtk.Builder()
builder.add_from_file(os.path.join(os.path.dirname(os.path.realpath(__file__)), "plotcommander.glade"))
def w(widgetname): return builder.get_object(widgetname)   # shortcut to access widgets 
builder.connect_signals(Handler())

window = builder.get_object("window1")
window.maximize()
window.show_all()

Gtk.main()


    # future todos:
    #  * select record by clicking in the graph, right-click menu in the list)
    #        http://scienceoss.com/interactively-select-points-from-a-plot-in-matplotlib/#more-14
    #        http://scienceoss.com/interacting-with-figures-in-python/
    #  * line as actor?   ... self.line, = self.Axes.plot([], [], animated=True)
    #                         self.background=self.canvas1.copy_from_bbox(self.Axes.bbox)
    #  * allow PDF graph export   
            # TODO - use icons?
            #w('treestore1').append(None, ['no', Gtk.IconTheme.get_default().load_icon('edit-cut', 16, 0), infile])
            # TODO - moving rows http://www.pygtk.org/pygtk2tutorial/sec-TreeModelInterface.html

            # TODO - on window resize, adjust borders? 
            # http://stackoverflow.com/questions/6066091/python-matplotlib-figure-borders-in-wxpython
