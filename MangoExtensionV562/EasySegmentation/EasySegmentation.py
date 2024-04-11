import logging
import os
from typing import Annotated, Optional

import vtk
import ctk
import qt
import glob
from xml.dom import minidom

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode

from pathlib import Path
import re


#
# EasySegmentation
#


class EasySegmentation(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("EasySegmentation")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Hanwool Park (Mango medical)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
This is an extension for people to segmentation and save files easily.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Hanwool Park, Mango medical.
See more information in <a href="https://www.mangomedical.de/">Homepage</a>
""")

     
#
# EasySegmentationParameterNode
#


@parameterNodeWrapper
class EasySegmentationParameterNode:
    """
    The parameters needed by module.

    inputVolume - The volume to threshold.
    imageThreshold - The value at which to threshold the input volume.
    invertThreshold - If true, will invert the threshold.
    thresholdedVolume - The output volume that will contain the thresholded volume.
    invertedVolume - The output volume that will contain the inverted thresholded volume.
    """

    inputVolume: vtkMRMLScalarVolumeNode
    imageThreshold: Annotated[float, WithinRange(-100, 500)] = 100
    invertThreshold: bool = False
    thresholdedVolume: vtkMRMLScalarVolumeNode
    invertedVolume: vtkMRMLScalarVolumeNode


#
# EasySegmentationWidget
#


class EasySegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

        # Members
        self.parameterSetNode = None
        self.editor = None
        self.saveDirectory = ""
        self.imageDirectory = ""
        self.segDirectory = ""
        self.current_file = 0
        self.total_files = 0
        self.needAddProperty = True
        self.changeProperty = False
        self.displayNode = None

        self.moduleName = self.__class__.__name__
        if self.moduleName.endswith('Widget'):
                self.moduleName = self.moduleName[:-6]

        # get version
        self.slicer_majorVersion = slicer.app.majorVersion
        self.slicer_minorVersion = slicer.app.minorVersion

        self.file_types = ('*.nrrd', '*.nii', '*.nii.gz')

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""

        def createHLayout(elements):
            rowLayout = qt.QHBoxLayout()
            for element in elements:
                    rowLayout.addWidget(element)
            return rowLayout

        ScriptedLoadableModuleWidget.setup(self)

        self.MainCollapsibleButton = ctk.ctkCollapsibleButton()
        self.MainCollapsibleButton.text = "Files"
        self.MainCollapsibleButton.collapsed = 0
        self.layout.addWidget(self.MainCollapsibleButton)
        MainFormLayout = qt.QFormLayout(self.MainCollapsibleButton)

        self.loadImageButton = qt.QPushButton("Image Folder")
        self.loadImageButton.toolTip = "Load image directory"
        self.loadImageButton.name = "Load image directory"
        self.loadImageButton.connect('clicked()', self.onLoadImage)

        self.loadSegButton = qt.QPushButton("Segmentation Folder")
        self.loadSegButton.toolTip = "Load segmentation directory"
        self.loadSegButton.name = "Load segmentation directory"
        self.loadSegButton.connect('clicked()', self.onLoadSeg)

        self.RunButton = qt.QPushButton("Load")
        self.RunButton.toolTip = "Load image and segmentation"
        self.RunButton.name = "Load"
        self.RunButton.connect('clicked()', self.onRun)

        self.DirButton = qt.QPushButton(self.saveDirectory)
        self.DirButton.toolTip = "destination folder"
        self.DirButton.name = "destination"
        self.DirButton.connect('clicked()', self.onDir)

        self.ImageCheck = qt.QCheckBox("Image")
        self.ImageCheck.setChecked(False)
        self.ImageCheck.connect('clicked()', self.onImageCheck)

        self.SegCheck = qt.QCheckBox("Segmentation")
        self.SegCheck.setChecked(True)
        self.SegCheck.connect('clicked()', self.onSegCheck)

        self.SaveButton = qt.QPushButton("Save")
        self.SaveButton.toolTip = "Save files"
        self.SaveButton.name = "Save files"
        self.SaveButton.connect('clicked()', self.onSave)

        self.PreButton = qt.QPushButton("Previous")
        self.PreButton.toolTip = "Previous file"
        self.PreButton.name = "Previous file"
        self.PreButton.connect('clicked()', self.onPre)

        self.NextButton = qt.QPushButton("Next")
        self.NextButton.toolTip = "Next file"
        self.NextButton.name = "Next file"
        self.NextButton.connect('clicked()', self.onNext)

        self.ResetButton = qt.QPushButton("Reset")
        self.ResetButton.toolTip = "Reset Module"
        self.ResetButton.name = "Reset"
        self.ResetButton.connect('clicked()', self.onReset)

        # add suffix to save name
        self.suffixBox = qt.QTextEdit()
        self.suffixBox.setFixedSize(100, 23) # Set the size of the widget
        self.suffixBox.setText("_seg")

        self.suffixButton = qt.QPushButton("Apply Suffix Naming")
        self.suffixButton.toolTip = "apply suffix naming in segmentation file"
        self.suffixButton.name = "Suffix"
        self.suffixButton.setCheckable(True)
        self.suffixButton.connect('clicked(bool)', self.onSuffix)

        self.suffixButton.enabled = True

        self.suffixButton.setChecked(1)

        self.FileComboBox = qt.QComboBox()
        self.FileComboBox.currentIndexChanged.connect(self.onFileCombo)
        # self.FileComboBox.connect(self.onFileCombo)

        self.RenderCheck = qt.QCheckBox("On")
        self.RenderCheck.setChecked(False)
        self.RenderCheck.connect('clicked()', self.onRenderingCheck)

        self.ThresholdCheck = qt.QCheckBox("On")
        self.ThresholdCheck.setChecked(False)
        self.ThresholdCheck.connect('clicked()', self.onThresholdCheck)

        self.minBox = qt.QTextEdit()
        self.minBox.setFixedSize(50, 23) # Set the size of the widget
        self.minBox.setText("0.1")
        self.minBox.setDisabled(True)

        self.maxBox = qt.QTextEdit()
        self.maxBox.setFixedSize(50, 23) # Set the size of the widget
        self.maxBox.setText("100000")
        self.maxBox.setDisabled(True)

        self.ApplyButton = qt.QPushButton("Apply")
        self.ApplyButton.toolTip = "apply threshold"
        self.ApplyButton.name = "apply threshold"
        self.ApplyButton.connect('clicked()', self.onApply)
        self.ApplyButton.setDisabled(True)

        minLabel = qt.QLabel("Min:")
        emptyLabel = qt.QLabel(" ")
        maxLabel = qt.QLabel("Max:")

        MainFormLayout.addRow(createHLayout([self.loadImageButton, self.loadSegButton, self.RunButton]))
        MainFormLayout.addRow(createHLayout([self.PreButton, self.NextButton, self.ResetButton]))
        MainFormLayout.addRow("destination folder : ", createHLayout([self.DirButton]))
        MainFormLayout.addRow("node to save : ",createHLayout([self.ImageCheck, self.SegCheck, self.SaveButton]))
        MainFormLayout.addRow("suffix segmentation name : ",createHLayout([self.suffixBox, self.suffixButton]))
        MainFormLayout.addRow("file list : ",createHLayout([self.FileComboBox]))
        MainFormLayout.addRow("Automatic Volume Rendering : ",createHLayout([self.RenderCheck]))
        MainFormLayout.addRow("Threshold ",createHLayout([self.ThresholdCheck, minLabel, self.minBox, emptyLabel, maxLabel, self.maxBox, self.ApplyButton]))

        #
        # Volume rendering 
        #

        # new collapse button
        self.renderCollapsibleButton = ctk.ctkCollapsibleButton()
        self.renderCollapsibleButton.text = "Volume Rendering"
        self.renderCollapsibleButton.collapsed = 1
        self.layout.addWidget(self.renderCollapsibleButton)
        renderFormLayout = qt.QFormLayout(self.renderCollapsibleButton)

        # volume rendering
        import qSlicerVolumeRenderingModuleWidgetsPythonQt

        self.render = qSlicerVolumeRenderingModuleWidgetsPythonQt.qSlicerVolumeRenderingPresetComboBox()
        self.render.setMRMLScene(slicer.mrmlScene)
        self.render.enabled = False

        self.PresetComboBox = self.render.findChild("qSlicerPresetComboBox", "PresetComboBox")

        self.PresetComboBox.connect("currentNodeIDChanged(const QString &)", self.onPresetCombo)

        self.OldPresetPosition = 0

        self.PresetOffsetSlider = self.render.findChild("ctkDoubleSlider", "PresetOffsetSlider")
        self.PresetOffsetSlider.connect("sliderPressed", self.startInteraction)
        self.PresetOffsetSlider.connect("valueChanged(double)", self.offsetPreset)
        self.PresetOffsetSlider.connect("valueChanged(double)", self.interaction)
        self.PresetOffsetSlider.connect("sliderReleased", self.endInteraction)

        renderFormLayout.addRow(self.render)

        self.RenderButton = qt.QPushButton("Display Volume Rendering")
        self.RenderButton.toolTip = "display volume rendering button"
        self.RenderButton.name = "Rendering"
        self.RenderButton.setCheckable(True)
        self.RenderButton.connect('clicked(bool)', self.onRendering)

        self.RenderButton.enabled = False

        renderFormLayout.addRow(createHLayout([self.RenderButton]))


        #
        # Segment editor widget
        #

        # new collapse button
        self.editorCollapsibleButton = ctk.ctkCollapsibleButton()
        self.editorCollapsibleButton.text = "Segmentation Editor"
        self.editorCollapsibleButton.collapsed = 1
        self.layout.addWidget(self.editorCollapsibleButton)
        editorFormLayout = qt.QFormLayout(self.editorCollapsibleButton)
        
        import qSlicerSegmentationsModuleWidgetsPythonQt
        self.editor = qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget()
        self.editor.setMaximumNumberOfUndoStates(10)

        self.editor.setMRMLScene(slicer.mrmlScene)

        editorFormLayout.addRow(self.editor)

        self.selectParameterNode()

        verticalSpacer = qt.QSpacerItem(20, 40, qt.QSizePolicy.Minimum, qt.QSizePolicy.Expanding)
        self.layout.addItem(verticalSpacer)

        # Observe editor effect registrations to make sure that any effects that are registered
        # later will show up in the segment editor widget. For example, if Segment Editor is set
        # as startup module, additional effects are registered after the segment editor widget is created.
        self.effectFactorySingleton = slicer.qSlicerSegmentEditorEffectFactory.instance()
        self.effectFactorySingleton.connect('effectRegistered(QString)', self.editorEffectRegistered)

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    def selectParameterNode(self):
            # Select parameter set node if one is found in the scene, and create one otherwise
            segmentEditorSingletonTag = "SegmentEditor"
            segmentEditorNode = slicer.mrmlScene.GetSingletonNode(segmentEditorSingletonTag, "vtkMRMLSegmentEditorNode")
            if segmentEditorNode is None:
                    segmentEditorNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
                    segmentEditorNode.UnRegister(None)
                    segmentEditorNode.SetSingletonTag(segmentEditorSingletonTag)
                    segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
            if self.parameterSetNode == segmentEditorNode:
                    # nothing changed
                    return
            self.parameterSetNode = segmentEditorNode
            self.editor.setMRMLSegmentEditorNode(self.parameterSetNode)


    def onSuffix(self):

        pass


    def onThresholdCheck(self):

        if self.ThresholdCheck.isChecked():
            self.minBox.setDisabled(False)
            self.maxBox.setDisabled(False)
            self.ApplyButton.setDisabled(False)

        else:
            self.minBox.setDisabled(True)
            self.maxBox.setDisabled(True)
            self.ApplyButton.setDisabled(True)

    def onApply(self):

        minValue = self.minBox.toPlainText()
        maxValue = self.maxBox.toPlainText()
        segmentId = self.currentSegNode.GetSegmentation().GetSegmentIdBySegmentName('Segment_1')

        if segmentId == "":
            self.NewSegmentId = self.currentSegNode.GetSegmentation().AddEmptySegment('Segment_1')
        else:
            self.NewSegmentId = segmentId

        # Get segment as numpy array
        segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(self.currentSegNode, self.NewSegmentId, self.currentVolumeNode)

        # Modify the segmentation
        segmentArray[:] = 0  # clear the segmentation
        volumeArray = slicer.util.arrayFromVolume(self.currentVolumeNode)
        segmentArray[(volumeArray >= float(minValue)) & (volumeArray <= float(maxValue))  ] = 1  # create segment by simple thresholding of an image
        slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, self.currentSegNode, self.NewSegmentId, self.currentVolumeNode)

    def onRenderingCheck(self):

        pass

    def onRendering(self):

        if self.RenderButton.isChecked():

            if self.displayNode:
                self.displayNode.SetVisibility(1)

        else:
            if self.displayNode:
                self.displayNode.SetVisibility(0)

    def onPresetCombo(self, id):

        if self.needAddProperty == False:

            if self.changeProperty == True:

                self.OldPresetPosition = 0.0
                self.PresetOffsetSlider.setValue(0.0)

                self.changeProperty = False

                self.currentPresetNode = self.newPresetNode
                self.render.setCurrentNode(self.newPresetNode)

                
            else:

                self.newPresetNode = slicer.mrmlScene.GetNodeByID(id)

                if self.currentPresetNode == self.newPresetNode:
                    return

                self.changeProperty = True
                self.render.setCurrentNode(self.currentPresetNode)
                            

        else:
            return

    def startInteraction(self):
        if self.volumePropertyNode:
            self.volumePropertyNode.InvokeEvent(vtk.vtkCommand.StartInteractionEvent)

    def endInteraction(self):
        if self.volumePropertyNode:
            self.volumePropertyNode.InvokeEvent(vtk.vtkCommand.EndInteractionEvent)

    def offsetPreset(self, newPosition):
        if not self.displayNode:
            return

        volRenWidget = slicer.modules.volumerendering.widgetRepresentation()
        volumePropertyNodeWidget = slicer.util.findChild(volRenWidget, 'VolumePropertyNodeWidget')
        volumePropertyNodeWidget.setMRMLVolumePropertyNode(self.volumePropertyNode)

        volumePropertyNodeWidget.moveAllPoints(newPosition - self.OldPresetPosition, 0, False)
        self.OldPresetPosition = newPosition

    def interaction(self):
        if self.volumePropertyNode:
            self.volumePropertyNode.InvokeEvent(vtk.vtkCommand.InteractionEvent)

    def onLoadImage(self):

            qfiledialog = qt.QFileDialog()
            # tuple_file_paths = qfiledialog.getOpenFileNames()  # Select file(s)
            self.imageDirectory = qfiledialog.getExistingDirectory()  # Select directory

            print("image folder : ", self.imageDirectory)

    def onLoadSeg(self):

            qfiledialog = qt.QFileDialog()
            # tuple_file_paths = qfiledialog.getOpenFileNames()  # Select file(s)
            self.segDirectory = qfiledialog.getExistingDirectory()  # Select directory

            print("segmentation foler : ", self.segDirectory)

    def onDir(self):

            qfiledialog = qt.QFileDialog()
            # tuple_file_paths = qfiledialog.getOpenFileNames()  # Select file(s)
            self.saveDirectory = qfiledialog.getExistingDirectory()  # Select directory

            self.DirButton.setText(self.saveDirectory)

    def onPre(self):

            if self.current_file == 0:
                slicer.util.warningDisplay('This is first file', windowTitle='Mangomedcial')
                return

            else:
                self.RemoveCurrentScene()
                self.current_file -= 1

            #self.LoadFiles()
            self.FileComboBox.setCurrentIndex(self.current_file)

    def onNext(self):

            if self.current_file + 1 == self.total_files:
                slicer.util.warningDisplay('This is last file', windowTitle='Mangomedcial')
                return

            else:

                # remove current node
                self.RemoveCurrentScene()
                self.current_file += 1

                #self.LoadFiles()
                self.FileComboBox.setCurrentIndex(self.current_file)

    def onImageCheck(self):
            pass

    def onSegCheck(self):
            pass

    def onFileCombo(self, index):

            if self.editor.segmentationNodeID():
                self.RemoveCurrentScene()

            if self.total_files != 0:
                self.current_file = index
                self.LoadFiles()

    def InsertFileCombo(self):

            for index in range(self.total_files):

                image_basename = os.path.basename(self.fileset[index][0])
                image_name = self.find_basename_wo_extension(self.fileset[index][0])

                self.FileComboBox.addItem(image_name)

    def RemoveCurrentNodes(self):

            slicer.mrmlScene.RemoveNode(self.currentVolumeNode)
            slicer.mrmlScene.RemoveNode(self.currentSegNode)

    def RemoveCurrentScene(self):

            slicer.mrmlScene.Clear(0)

    def onReset(self):

            self.saveDirectory = ""
            self.current_file = 0
            self.total_files = 0
            self.imageDirectory = ""
            self.segDirectory = ""
            self.fileset = []
            self.FileComboBox.clear()
            self.ImageCheck.setChecked(0)
            self.SegCheck.setChecked(1)
            self.RenderCheck.setChecked(0)

            self.minBox.setText("0.1") 
            self.maxBox.setText("100000")

            self.minBox.setDisabled(True)
            self.maxBox.setDisabled(True)
            self.ApplyButton.setDisabled(True)

            self.suffixBox.setText("_seg")
            self.suffixButton.setChecked(1)


            self.needAddProperty = True
            self.changeProperty = False
            self.RenderButton.enabled = False
            self.render.enabled = False

            self.DirButton.setText(self.saveDirectory)
            self.editorCollapsibleButton.collapsed = 1
            self.renderCollapsibleButton.collapsed = 1

            slicer.mrmlScene.Clear(0)

    def onRun(self):

            # check directory
            image_files = []
            seg_files = []

            for files in self.file_types:

                image_files.extend(sorted(glob.glob(os.path.join(self.imageDirectory, files))))
                seg_files.extend(sorted(glob.glob(os.path.join(self.segDirectory, files))))

            self.fileset = []

            num_onlyImage = 0

            # find corresponding files
            for image_file in image_files:

                    Is_Seg_Found = False

                    image_basename = os.path.basename(image_file)
                    image_name = self.find_basename_wo_extension(image_file)

                    image_name = re.sub(r"[_-]+", '_', image_name) # unify confuse hypen or dash characters.

                    for seg_file in seg_files:

                        seg_basename = os.path.basename(seg_file)
                        seg_name = self.find_basename_wo_extension(seg_file)

                        seg_name = re.sub(r"[_-]+", '_', seg_name)

                        if (image_name in seg_name) or (seg_name in image_name):
                            self.fileset.append([image_file, seg_file])
                            Is_Seg_Found = True
                            break

                    if Is_Seg_Found == False:
                        self.fileset.append([image_file, ""])
                        num_onlyImage += 1


            self.total_files = len(self.fileset)
            self.current_file = 0

            self.editorCollapsibleButton.collapsed = 0

            print('the number of total file set : ', self.total_files)
            print('the number of only image file set : ', num_onlyImage)

            #add file list into combobox
            self.InsertFileCombo()
            
            #load first file
            #self.LoadFiles()

    def find_basename_wo_extension(self, filepath):

        file_basename = os.path.basename(filepath)

        for types in self.file_types:

            if file_basename.find(types[1:]) != -1:
                return file_basename[:file_basename.find(types[1:])]

        return file_basename


    def onSave(self):

            if self.saveDirectory == "":
                slicer.util.warningDisplay('You must set destination folder', windowTitle='Mangomedcial')
                return

            elif self.total_files == 0:
                slicer.util.warningDisplay('You must load file first', windowTitle='Mangomedcial')
                return

            else:

                if self.ImageCheck.isChecked():
                    # save volume
                    volume_directory = os.path.join(self.saveDirectory, "image")

                    if not os.path.exists(volume_directory):
                        os.makedirs(volume_directory)

                    #volumeNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLScalarVolumeNode')
                    volumeFile = os.path.basename(self.fileset[self.current_file][0])
                    volumeFileName = self.find_basename_wo_extension(self.fileset[self.current_file][0])
                    volume_path = os.path.join(volume_directory, volumeFileName + ".nii.gz")

                    if self.slicer_majorVersion >= 5 and self.slicer_minorVersion >= 2:
                        slicer.util.exportNode(self.currentVolumeNode, volume_path)

                    else:
                        slicer.util.saveNode(self.currentVolumeNode, volume_path)
                    

                if self.SegCheck.isChecked():

                    # save segmentation
                    seg_directory = os.path.join(self.saveDirectory, "segmentation")
                    
                    if not os.path.exists(seg_directory):
                        os.makedirs(seg_directory)

                    #segmentationNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLSegmentationNode")
                    labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
                    slicer.modules.segmentations.logic().ExportAllSegmentsToLabelmapNode(self.currentSegNode, labelmapVolumeNode, slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY)
                    
                    if self.fileset[self.current_file][1] != "":
                        segFile = os.path.basename(self.fileset[self.current_file][1])
                    else:
                        segFile = self.currentSegNode.GetName()
                    
                    segFileName = self.find_basename_wo_extension(segFile)

                    if self.suffixButton.isChecked():
                        seg_path = os.path.join(seg_directory, segFileName + "{}.nii.gz".format(self.suffixBox.toPlainText()))

                    else:
                        seg_path = os.path.join(seg_directory, segFileName + ".nii.gz")

                    
                    if self.slicer_majorVersion >= 5 and self.slicer_minorVersion >= 2:
                        slicer.util.exportNode(labelmapVolumeNode, seg_path)
                    else:
                        slicer.util.saveNode(labelmapVolumeNode, seg_path)

                    slicer.mrmlScene.RemoveNode(labelmapVolumeNode.GetDisplayNode().GetColorNode())
                    slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    def LoadFiles(self):

            # check volume rendering property needs to add or not + can be change property or not
            self.needAddProperty = True
            self.changeProperty = False

            if self.RenderButton.isChecked():
                self.RenderButton.click()

            if self.imageDirectory == "":

                slicer.util.warningDisplay('Please choose image folder', windowTitle='Mangomedcial')
                return

            elif self.total_files == 0:

                slicer.util.warningDisplay('There are no file to load. Please check image folder and segmentation folder\n\
                    image folder : {}\n\
                    segmentation folder :{}'.format(self.imageDirectory, self.segDirectory), windowTitle='Mangomedcial')
                return

            else:

                image_basename = os.path.basename(self.fileset[self.current_file][0])
                image_name = self.find_basename_wo_extension(self.fileset[self.current_file][0])

                # load volume node and segmentation node
                self.currentVolumeNode = slicer.util.loadVolume(self.fileset[self.current_file][0])
                self.currentVolumeNode.SetName(image_name)

                if self.fileset[self.current_file][1] != "":
                    self.currentSegNode = slicer.util.loadSegmentation(self.fileset[self.current_file][1])
                    self.editor.setSegmentationNode(self.currentSegNode)

                    self.ThresholdCheck.setDisabled(True)
                    self.minBox.setDisabled(True)
                    self.maxBox.setDisabled(True)
                    self.ApplyButton.setDisabled(True)

                else : 
                    
                    self.ThresholdCheck.setDisabled(False)
                    self.onThresholdCheck()
                    
                    self.currentSegNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')
                    self.currentSegNode.CreateDefaultDisplayNodes() # only needed for display
                    self.currentSegNode.SetName(image_name)
                    self.currentSegNode.SetReferenceImageGeometryParameterFromVolumeNode(self.currentVolumeNode)

                    self.editor.setSegmentationNode(self.currentSegNode)
                    self.editor.setSourceVolumeNode(self.currentVolumeNode)

                    volumeArray = slicer.util.arrayFromVolume(self.currentVolumeNode)
                    maxVolume = volumeArray.max()

                    # self.minBox.setText("0.1") # keep previous minimum value
                    self.maxBox.setText("{}".format(maxVolume))

                    if self.ThresholdCheck.isChecked():

                        minValue = self.minBox.toPlainText()
                        maxValue = self.maxBox.toPlainText()

                        segmentId = self.currentSegNode.GetSegmentation().GetSegmentIdBySegmentName('Segment_1')

                        if segmentId == "":
                            self.NewSegmentId = self.currentSegNode.GetSegmentation().AddEmptySegment('Segment_1')
                        else:
                            self.NewSegmentId = segmentId
                    
                        # Get segment as numpy array
                        segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(self.currentSegNode, self.NewSegmentId, self.currentVolumeNode)

                        # Modify the segmentation
                        segmentArray[:] = 0  # clear the segmentation
                        
                        segmentArray[(volumeArray >= float(minValue)) & (volumeArray <= float(maxValue))  ] = 1  # create segment by simple thresholding of an image
                        slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, self.currentSegNode, self.NewSegmentId, self.currentVolumeNode)

                if self.slicer_majorVersion >= 5 and self.slicer_minorVersion >= 2:
                    self.editor.setSourceVolumeNode(self.currentVolumeNode)
                else:
                    self.editor.setMasterVolumeNode(self.currentVolumeNode)

                #run volume rendering
                self.renderCollapsibleButton.collapsed = 0
                scriptedModulesPath = os.path.dirname(slicer.util.modulePath(self.moduleName))
                presetfile = os.path.join(scriptedModulesPath, 'Resources', "presets.xml")
                mydoc = minidom.parse(presetfile)

                items = mydoc.getElementsByTagName('VolumeProperty')

            #     volRenLogic = slicer.modules.volumerendering.logic()
            # displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(self.currentVolumeNode)
            # displayNode.GetVolumePropertyNode().Copy(volRenLogic.GetPresetByName("CT-AAA"))
            # displayNode.SetVisibility(True)

                self.render.enabled = True
                self.RenderButton.enabled = True
                volRenLogic = slicer.modules.volumerendering.logic()
                self.displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(self.currentVolumeNode)
                # self.displayNode.GetVolumePropertyNode().Copy(volRenLogic.GetPresetByName("CT-AAA"))
                self.volumePropertyNode = self.displayNode.GetVolumePropertyNode()
                self.render.setMRMLVolumePropertyNode(self.volumePropertyNode)
                
                # add presets
                self.preset_nodes = []
                for item in items:
                    preset = volRenLogic.GetPresetByName(item.attributes['name'].value)
                    self.preset_nodes.append(slicer.mrmlScene.AddNode(preset))
                    # self.volumePropertyNode.Copy(self.preset_nodes[-1])

                self.needAddProperty = False
                
                self.currentPresetNode = self.preset_nodes[0]
                self.render.setCurrentNode(self.preset_nodes[0])

                # Center the 3D view on the scene
                layoutManager = slicer.app.layoutManager()
                threeDWidget = layoutManager.threeDWidget(0)
                threeDView = threeDWidget.threeDView()
                threeDView.resetFocalPoint()

                if self.RenderCheck.isChecked():
                    self.displayNode.SetVisibility(1)
                    self.RenderButton.setChecked(1)

                else:
                    self.displayNode.SetVisibility(0)					
                    self.RenderButton.setChecked(0)

    def editorEffectRegistered(self):
            self.editor.updateEffectList()

    def getDefaultSourceVolumeNodeID(self):
            layoutManager = slicer.app.layoutManager()
            firstForegroundVolumeID = None
            # Use first background volume node in any of the displayed layouts.
            # If no beackground volume node is in any slice view then use the first
            # foreground volume node.
            for sliceViewName in layoutManager.sliceViewNames():
                    sliceWidget = layoutManager.sliceWidget(sliceViewName)
                    if not sliceWidget:
                            continue
                    compositeNode = sliceWidget.mrmlSliceCompositeNode()
                    if compositeNode.GetBackgroundVolumeID():
                            return compositeNode.GetBackgroundVolumeID()
                    if compositeNode.GetForegroundVolumeID() and not firstForegroundVolumeID:
                            firstForegroundVolumeID = compositeNode.GetForegroundVolumeID()
            # No background volume was found, so use the foreground volume (if any was found)
            return firstForegroundVolumeID
                  
    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        # Set parameter set node if absent
        self.selectParameterNode()
        self.editor.updateWidgetFromMRML()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.selectParameterNode()
        self.editor.updateWidgetFromMRML()

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.selectParameterNode()
            self.editor.updateWidgetFromMRML()


#
# EasySegmentationLogic
#


class EasySegmentationLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return EasySegmentationParameterNode(super().getParameterNode())

    def process(self,
                inputVolume: vtkMRMLScalarVolumeNode,
                outputVolume: vtkMRMLScalarVolumeNode,
                imageThreshold: float,
                invert: bool = False,
                showResult: bool = True) -> None:
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param imageThreshold: values above/below this threshold will be set to 0
        :param invert: if True then values above the threshold will be set to 0, otherwise values below are set to 0
        :param showResult: show output volume in slice viewers
        """

        if not inputVolume or not outputVolume:
            raise ValueError("Input or output volume is invalid")

        import time

        startTime = time.time()
        logging.info("Processing started")

        # Compute the thresholded output volume using the "Threshold Scalar Volume" CLI module
        cliParams = {
            "InputVolume": inputVolume.GetID(),
            "OutputVolume": outputVolume.GetID(),
            "ThresholdValue": imageThreshold,
            "ThresholdType": "Above" if invert else "Below",
        }
        cliNode = slicer.cli.run(slicer.modules.thresholdscalarvolume, None, cliParams, wait_for_completion=True, update_display=showResult)
        # We don't need the CLI module node anymore, remove it to not clutter the scene with it
        slicer.mrmlScene.RemoveNode(cliNode)

        stopTime = time.time()
        logging.info(f"Processing completed in {stopTime-startTime:.2f} seconds")


#
# EasySegmentationTest
#


class EasySegmentationTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_EasySegmentation1()

    def test_EasySegmentation1(self):
        """Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData

        registerSampleData()
        inputVolume = SampleData.downloadSample("EasySegmentation1")
        self.delayDisplay("Loaded test data set")

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = EasySegmentationLogic()

        # Test algorithm with non-inverted threshold
        logic.process(inputVolume, outputVolume, threshold, True)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.process(inputVolume, outputVolume, threshold, False)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay("Test passed")
