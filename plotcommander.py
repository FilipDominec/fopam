#!/usr/bin/python3
#-*- coding: utf-8 -*-
import gi, sys, os, signal, stat, traceback
import numpy as np
import robust_csv_parser

## Plotting dependencies and settings
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository.GdkPixbuf import Pixbuf,Colorspace

import matplotlib
from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo  as FigureCanvas # "..Agg" backend is broken currently
from matplotlib.backends.backend_gtk3      import NavigationToolbar2GTK3 as NavigationToolbar
import pandas as pd


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
        self.tsFiles = Gtk.TreeStore(str,        Pixbuf, str,        Pixbuf,            int)
        ## column meaning:           0:filepath  1:icon  2:name      3:plotstyleicon    4:column
        self.dummy_treestore_row = [None, None, None, None, None]

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
        w('treeview1').get_selection().set_select_function(self.treeview1_selectmethod, data=None) # , full=True

        ## TODO: If files are specified as arguments, select these at start, and plot them at once

        ## If a directory is specified, just set it as the root of the file list. If none, use current working dir.
        self.treeViewRootDir = os.getcwd() if len(sys.argv)<=1  else  sys.argv[1]
        self.populateTreeStore(self.tsFiles, basepath=self.treeViewRootDir, parent=None, include_up_dir=True)
        self.plot_reset()
        self.plot_all_sel_records()


        ## Add the data cursor by default  # TODO - make this work
        from matplotlib.widgets import Cursor
        cursor = Cursor(self.ax, useblit=True, color='red', linewidth=2)

        #}}}
    ## === FILE HANDLING ===
    def clearAllPlotIcons(self, treeIter):# {{{
        while treeIter != None: 
            iterpixbuf = self.tsFiles.get_value(treeIter, 3)
            if iterpixbuf: iterpixbuf.fill(self.array2rgbhex([.5,.5,1], alpha=0)) ## some nodes may have pixbuf set to None
            self.clearAllPlotIcons(self.tsFiles.iter_children(treeIter))
            treeIter=self.tsFiles.iter_next(treeIter)
        # }}}
    def isFolder(self, itemFullName): # {{{
        try:
            return stat.S_ISDIR(os.stat(itemFullName).st_mode) # Extract metadata from the item
        except:
            return False    ## catch errors - the user might supply, e.g., a name of a data column
        # }}}
    def isMulticolumnFile(self, itemFullName): # {{{
        try:                    
            data_array, header, parameters = robust_csv_parser.loadtxt(itemFullName, sizehint=1000)
            return len(header)>2
        except (IOError, RuntimeError):    # This error is usually returned for directories and non-data files
            return False
        # }}}
    def populateTreeStore(self, treeStore, basepath, parent=None, include_up_dir=False):
        ## Returns whether the row at basepath can be selected

        ## If we update the whole tree, it has to be cleared first. 
        ## During this operation, its selection will change, but the plots should not be updated so that it is fast.
        if parent == None:
            self.lockTreeViewEvents = True
            self.tsFiles.clear()
            self.clearAllPlotIcons(self.tsFiles.get_iter_first())
            self.treeViewRootDir = basepath
            self.lockTreeViewEvents = False

        ## The first node may point to the above directory, enabling the user to browse whole filesystem (used together with parent=None)
        if include_up_dir:
            itemIcon = Gtk.IconTheme.get_default().load_icon('go-up', 8, 0) # Generate a default icon
            plotstyleIcon = Pixbuf.new(Colorspace.RGB, True, 8, 10, 10)
            plotstyleIcon.fill(0xffffffff)
            currentIter = treeStore.append(parent, [basepath, itemIcon, '..', plotstyleIcon, -1])  # Append the item to the TreeStore
            treeStore.append(currentIter, self.dummy_treestore_row)

        if self.isFolder(basepath):
            ## Populate a folder with files/subdirs in a directory
            itemFullNames = [os.path.join(basepath, filename) for filename in os.listdir(basepath)]

            ## Filter the files
            fileFilterString = w('enFileFilter').get_text().strip()
            if fileFilterString != "":
                itemFullNames = [itemFullName for itemFullName in itemFullNames 
                        if (fileFilterString in os.path.basename(itemFullName) or self.isFolder(itemFullName))]

            ## Sort alphabetically, all folders above files
            itemFullNames.sort()
            itemFullNames = [f for f in itemFullNames if self.isFolder(f)] + [f for f in itemFullNames if not self.isFolder(f)] 

            ## Populate the node
            itemCounter = 0
            for itemFullName in itemFullNames:
                isFolder, isMultiColumnFile = self.isFolder(itemFullName),  self.isMulticolumnFile(itemFullName)
                itemIcon = Gtk.IconTheme.get_default().load_icon('folder' if isFolder else 
                        ('zip' if isMultiColumnFile else 'empty'), 8, 0)
                displayedName = os.path.basename(itemFullName)
                plotstyleIcon = Pixbuf.new(Colorspace.RGB, True, 8, 10, 10)
                plotstyleIcon.fill(0xffffffff)
                currentIter = treeStore.append(parent, [itemFullName, itemIcon, displayedName, plotstyleIcon, -1])
                if isFolder or isMultiColumnFile:  
                    treeStore.append(currentIter, self.dummy_treestore_row)      # add dummy if current item was a folder
                itemCounter += 1                                    #increment the item counter
            if itemCounter < 1: treeStore.append(parent, self.dummy_treestore_row)        # add the dummy node back if nothing was inserted before
        elif self.isMulticolumnFile(basepath):          ## Multicolumn means x-column and two or more y-columns
            data_array, header, parameters = robust_csv_parser.loadtxt(basepath, sizehint=1000)
            ## Populate a file with files/subdirs in a directory
            columnNames = header

            ## Filter the column names TODO
            #columnFilterString = w('enColumnFilter').get_text().strip()
            #if columnFilterString != "":
                #itemFullNames = [item for item in itemFullNames 
                        #if (columnFilterString in os.path.basename(itemFullName) or self.isFolder(itemFullName))]

            ## Populate the node
            itemCounter = 0
            for columnNumber, columnName in enumerate(columnNames):
                itemIcon = Gtk.IconTheme.get_default().load_icon('go-next', 8, 0)
                plotstyleIcon = Pixbuf.new(Colorspace.RGB, True, 8, 10, 10)
                plotstyleIcon.fill(0xffffffff)
                currentIter = treeStore.append(parent, [basepath, itemIcon, columnName, plotstyleIcon, columnNumber])
                itemCounter += 1                                    #increment the item counter
            if itemCounter < 1: treeStore.append(parent, self.dummy_treestore_row)        # add the dummy node back if nothing was inserted before
        elif basepath[-4:] == ".opj":
            warnings.warn("Not implemented: Origin projects plotting not implemented yet")
        else:
            print("Warning: file type not recognized")

        ## Register a new record in the record table
        self.record_labels[file_path] = os.path.basename(file_path) 
        self.record__types[file_path] = 'file'

    ## === FILE HANDLING ===
    def populateFileSystemTreeStore(self, treeStore, filepath, parent=None):
        itemCounter = 0
        listdir = os.listdir(filepath)
        listdir.sort()
        for item in listdir:                           # iterate over the items in the filepath
            itemFullname = os.path.join(filepath, item)             # Get the absolute filepath of the item
            itemMetaData = os.stat(itemFullname) 
            itemIsFolder = stat.S_ISDIR(itemMetaData.st_mode) # Extract metadata from the item
            if itemIsFolder:
                icon = 'folder' # Determine if the item is a folder
            elif item[-4:] == '.dat':
                icon = 'empty'   ## if can not load, change icon to stock_dialog-warning
            else:
                icon = 'gtk-stop' 
            itemIcon = Gtk.IconTheme.get_default().load_icon(icon, 8, 0) # Generate a default icon




            #import cairo
#
            #WIDTH, HEIGHT = 256, 256
#
            #surface = cairo.ImageSurface (cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
            #ctx = cairo.Context (surface)
#
            #ctx.scale (WIDTH, HEIGHT) # Normalizing the canvas
#
            #pat = cairo.LinearGradient (0.0, 0.0, 0.0, 1.0)
            #pat.add_color_stop_rgba (1, 0.7, 0, 0, 0.5) # First stop, 50% opacity
            #pat.add_color_stop_rgba (0, 0.9, 0.7, 0.2, 1) # Last stop, 100% opacity
#
            #ctx.rectangle (0, 0, 1, 1) # Rectangle(x0, y0, x1, y1)
            #ctx.set_source (pat)
            #ctx.fill ()
#
            #ctx.translate (0.1, 0.1) # Changing the current transformation matrix
#
            #ctx.move_to (0, 0)
            #ctx.arc (0.2, 0.1, 0.1, -3./2, 0) # Arc(cx, cy, radius, start_angle, stop_angle)
            #ctx.line_to (0.5, 0.1) # Line to (x,y)
            #ctx.curve_to (0.5, 0.2, 0.5, 0.4, 0.2, 0.8) # Curve(x1, y1, x2, y2, x3, y3)
            #ctx.close_path ()
#
            #ctx.set_source_rgb (0.3, 0.2, 0.5) # Solid color
            #ctx.set_line_width (0.02)
            #ctx.stroke ()


            ##TODO
            #plotstyleIcon = Gtk.IconTheme.get_default().load_icon('empty', 8, 0) # Generate a default icon ## WORKS
            #plotstyleIcon = Pixbuf.new_from_file_at_size("img/logo.png", 125, 125) ## WORKS

            pixbuf = Pixbuf.new_from_file_at_size("img/logo.png", 125, 125) # Generate a default icon

#           drawable = Gdk.cairo_create(pixbuf)
#           #drawable = Gtk.GdkPixmap(None, 30, 30, 24)
#           gc = drawable.new_gc()
#           #drawable.draw_pixbuf(gc, pixbuf, 0, 0, 0, 0, -1, -1)
#           gc.set_foreground(Gtk.Gdk.Color(65535, 0, 0))
#           drawable.draw_line(gc, 0, 0, w, h)
#
#           cmap = Gtk.Gdk.Colormap(Gtk.Gdk.visual_get_best(), False)
#           pixbuf.get_from_drawable(drawable, cmap, 0, 0, 0, 0, w, h)


            plotstyleIcon = pixbuf

#s = cairo_image_surface_create (CAIRO_FORMAT_A1, 3, 3);
#cr = cairo_create (s);
#cairo_arc (cr, 1.5, 1.5, 1.5, 0, 2 * M_PI);
#cairo_fill (cr);
#cairo_destroy (cr);
#
#pixbuf = gdk_pixbuf_get_from_surface (s,
                                      #0, 0,
                                      #3, 3);
#
#cairo_surface_destroy (s);

            ## OPTION 4
            #cairo_context = self.canvas.get_window().cairo_create()
            #window = w('treeview1').get_window()
            #ctx = Gdk.cairo_create(window)
            #ctx.set_source_pixbuf(pixbuf, 0, 0)
            #self.image = cairo.ImageSurface.create_from_png('img/logo.png')

            ## OPTION 5
            # ?? Gdk.cairo_set_source_pixbuf() 







            currentIter = treeStore.append(parent, [itemFullname, itemIcon, item, plotstyleIcon])  # Append the item to the TreeStore
            if itemIsFolder: treeStore.append(currentIter, self.dummy_treestore_row)      # add dummy if current item was a folder
            itemCounter += 1                                    #increment the item counter
        if itemCounter < 1: treeStore.append(parent, self.dummy_treestore_row)        # add the dummy node back if nothing was inserted before

    def onRowExpanded(self, treeView, treeIter, treePath):
        treeStore = treeView.get_model()        # get the associated model
        newPath = treeStore.get_value(treeIter, 0)      # get the full path of the position
        self.populateFileSystemTreeStore(treeStore, newPath, treeIter)       # populate the subtree on curent position
        treeStore.remove(treeStore.iter_children(treeIter))         # remove the first child (dummy node)

    def onRowCollapsed(self, treeView, treeIter, treePath):
        treeStore = treeView.get_model()        # get the associated model
        currentChildIter = treeStore.iter_children(treeIter)        # get the iterator of the first child
        while currentChildIter:         # loop as long as some childern exist
            treeStore.remove(currentChildIter)      # remove the first child
            currentChildIter = treeStore.iter_children(treeIter)        # refresh the iterator of the next child
        treeStore.append(treeIter, self.dummy_treestore_row)      # append dummy node
    

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
        color_pre_map = np.linspace(0.05, .95, len(pathlist)+1)[:-1]
        color_palette = matplotlib.cm.gist_rainbow(color_pre_map*.5 + np.sin(color_pre_map*np.pi/2)**2*.5)

        ## Plot all curves sequentially
        error_counter = 0
        for (path, color_from_palette) in zip(pathlist, color_palette):
            try:
                ## Plot the line first
                file_name       = self.tsFiles.get_value(self.tsFiles.get_iter(path), 0)
                column_number   = self.tsFiles.get_value(self.tsFiles.get_iter(path), 4)
                self.plot_record(file_name, 
                        xcolumn=0, ycolumn=column_number if column_number>0 else 1, 
                        plot_style={'color':color_from_palette})

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

        ## Load the data
        if   self.guess_file_type(infile) == 'opj':
            return ## NOTE: support for liborigin not tested yet! 
        elif self.guess_file_type(infile) == 'xls':
            xl = pd.ExcelFile(infile, header=1) ##  
            ## TODO: print(xl.sheet_names)    a XLS file is a *container* with multiple sheets, a sheet may contain multiple columns
            df = xl.parse() 
            x,y = df.values.T[xcolumn], df.values.T[ycolumn] ## TODO Should offer choice of columns ## FIXME clash with 'header'!!
        else:             ## for all remaining filetypes, try to interpret as a text table
            #from io import StringIO ## this is just a hack to avoid loading different comment lines
            #output = StringIO(); output.writelines(line for line in open(infile) if line[:1] not in "!;,%"); output.seek(0)
            #df = pd.read_csv(output, comment='#', delim_whitespace=True, error_bad_lines=False) 
            #output.close()
            #x, y = df.values.T[0], df.values.T[1] ## TODO: selection of columns!
            data_array, header, parameters = robust_csv_parser.loadtxt(infile, sizehint=1000000)
            x, y, header = data_array.T[xcolumn], data_array.T[ycolumn], header

        #try:
            #x, y = self.safe_to_float(x, y, x0=[float(header[xcolumn])], y0=[float(header[ycolumn])])
            #xlabel, ylabel = "x", "y"
        #except ValueError:      ## if conversion fails, use the first row as column names instead
            #x, y = self.safe_to_float(x, y, x0=[], y0=[])
            #xlabel, ylabel = header[xcolumn], header[ycolumn]

            #print("Warning, file %s could not be loaded as data file" % infile)
        self.ax.plot(x, y, label=os.path.basename(infile), **plot_style) # TODO apply plotting options
        self.ax.set_xlabel(header[xcolumn])
        self.ax.set_ylabel(header[ycolumn])
        #except:
            #pass
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

    ## == USER INTERFACE HANDLERS ==
    def on_treeview1_row_expanded(self, treeView, treeIter, treePath):# {{{
        ## if present, remove the dummy node (which is only used to draw the expander arrow)
        treeStore = treeView.get_model()
        newFilePath = treeStore.get_value(treeIter, 0)      # get the full path of the position

        ## Add the children 
        self.populateTreeStore(treeStore, newFilePath, treeIter)
        ## The dummy row has to be removed AFTER this, otherwise the empty treeView row will NOT expand)
        if treeStore.iter_children(treeIter):  
            treeStore.remove(treeStore.iter_children(treeIter))         
    def on_treeview1_row_collapsed(self, treeView, treeIter, treePath):# {{{ 
        ## Remove all child nodes of the given row (useful mostly to prevent de-syncing from some changes in the filesystem)
        #if self.lockTreeViewEvents: return      ## prevent event handlers triggering other events
        currentChildIter = self.tsFiles.iter_children(treeIter)
        while currentChildIter:         
            self.tsFiles.remove(currentChildIter)
            currentChildIter = self.tsFiles.iter_children(treeIter)
        self.tsFiles.append(treeIter, self.dummy_treestore_row)
    # }}}
    def on_treeview1_selection_changed(self, *args):# {{{       ## triggers replot
        if self.lockTreeViewEvents: return      ## prevent event handlers triggering other events
        ## Update the graphical presentation
        self.plot_reset()               ## first delete the curves, to hide (also) unselected plots
        self.plot_all_sel_records()     ## then show the selected ones
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()
    # }}}
    def treeview1_selectmethod(self, selection, model, treePath, is_selected, user_data):# {{{
        ## TODO reasonable behaviour for block-selection over different unpacked directories/files
        ## Expand a directory by clicking, but do not allow user to select it
        treeIter        = self.tsFiles.get_iter(treePath)
        fileNamePath    = self.tsFiles.get_value(treeIter, 0)
        columnNumber    = self.tsFiles.get_value(treeIter, 4)

        #if self.lockTreeViewEvents: return      ## prevent event handlers triggering other events OBSOLETED?

        ## Actions must be available even on un-selectable rows:
        selected_row_names = self.remember_treeView_selected_rows(self.tsFiles, w('treeview1'))
        if self.isFolder(fileNamePath) or (self.isMulticolumnFile(fileNamePath) and columnNumber in (None, -1, 0)):
            if self.tsFiles.get_value(treeIter, 2) == "..":  
                ## If the expanded row was "..", do not expand it, instead change to up-dir and refresh whole tree
                expanded_row_names = self.remember_treeView_expanded_rows(self.tsFiles, w('treeview1'))    
                selected_row_names = self.remember_treeView_selected_rows(self.tsFiles, w('treeview1'))
                self.populateTreeStore(self.tsFiles, basepath=os.path.dirname(self.treeViewRootDir), 
                        parent=None, include_up_dir=True)       
                #self.restore_treeView_expanded_rows(expanded_row_names) TODO TEST
                #self.restore_treeView_selected_rows(selected_row_names) TODO TEST
            elif w('treeview1').row_expanded(treePath):
                w('treeview1').collapse_row(treePath)
            elif not w('treeview1').row_expanded(treePath) :
                w('treeview1').expand_row(treePath, open_all=False)
            #self.restore_treeView_selected_rows(selected_row_names)
            return False
        else:
            return True

# }}}
    def on_enFileFilter_activate(self, *args):# {{{
        expanded_row_names = self.remember_treeView_expanded_rows(self.tsFiles, w('treeview1'))    
        selected_row_names = self.remember_treeView_selected_rows(self.tsFiles, w('treeview1'))
        # Passing parent=None will populate the whole tree again
        #self.lockTreeViewEvents = True
        self.populateTreeStore(self.tsFiles, basepath=self.treeViewRootDir, parent=None, include_up_dir=True)       
        #self.lockTreeViewEvents = False
        self.restore_treeView_expanded_rows(expanded_row_names)
        self.restore_treeView_selected_rows(selected_row_names)
        # }}}
    def on_enFileFilter_focus_out_event(self, *args):# {{{
        self.on_enFileFilter_activate(self)
    # }}}
    def on_enColFilter_activate(self, *args):# {{{ TODO
        pass
    def on_enColFilter_focus_out_event(self, *args):
        pass
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
