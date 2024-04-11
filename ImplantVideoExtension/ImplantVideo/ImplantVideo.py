import logging
import os
import glob
from typing import Annotated, Optional

import vtk
import qt
import ctk


import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

import ScreenCapture

from slicer import vtkMRMLScalarVolumeNode

try:
    from moviepy.editor import ImageSequenceClip
except:
    slicer.util.pip_install('moviepy')
    from moviepy.editor import ImageSequenceClip


#
# ImplantVideo
#


class ImplantVideo(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("ImplantVideo")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Hanwool Park (Mangomedical)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
This is an extension for people to extract implant from volume data and save 360 degree video easily..
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Hanwool Park, Mango medical.
See more information in <a href="https://www.mangomedical.de/">Homepage</a>
""")

#
# ImplantVideoParameterNode
#


@parameterNodeWrapper
class ImplantVideoParameterNode:
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
# ImplantVideoWidget
#


class ImplantVideoWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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

        self.saveDirectory = ""
        self.imageDirectory = ""
        self.segDirectory = ""
        self.currentVolumeNode = ""
        self.current_file = 0
        self.total_files = 0

    def setup(self) -> None:

        def createHLayout(elements):
            rowLayout = qt.QHBoxLayout()
            for element in elements:
                    rowLayout.addWidget(element)
            return rowLayout
        
        """Called when the user opens the module the first time and the widget is initialized."""
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

        self.RunButton = qt.QPushButton("Load")
        self.RunButton.toolTip = "Load image and segmentation"
        self.RunButton.name = "Load"
        self.RunButton.connect('clicked()', self.onRun)

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

        self.DirButton = qt.QPushButton(self.saveDirectory)
        self.DirButton.toolTip = "destination folder"
        self.DirButton.name = "destination"
        self.DirButton.connect('clicked()', self.onDir)

        self.FileComboBox = qt.QComboBox()
        self.FileComboBox.currentIndexChanged.connect(self.onFileCombo)

        self.CreateVideoButton = qt.QPushButton("Create Video")
        self.CreateVideoButton.toolTip = "Create Video Module"
        self.CreateVideoButton.name = "Create Video"
        self.CreateVideoButton.connect('clicked()', self.onCreateVideo)

        MainFormLayout.addRow(createHLayout([self.loadImageButton, self.RunButton]))
        MainFormLayout.addRow(createHLayout([self.PreButton, self.NextButton, self.ResetButton]))
        MainFormLayout.addRow("destination folder : ", createHLayout([self.DirButton]))
        MainFormLayout.addRow("file list : ",createHLayout([self.FileComboBox]))
        MainFormLayout.addRow(createHLayout([self.CreateVideoButton]))

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    def onLoadImage(self):

        qfiledialog = qt.QFileDialog()
        # tuple_file_paths = qfiledialog.getOpenFileNames()  # Select file(s)
        self.imageDirectory = qfiledialog.getExistingDirectory()  # Select directory

        print("image folder : ", self.imageDirectory)

    def onRun(self):

        # check directory
        self.fileset = sorted(glob.glob(os.path.join(self.imageDirectory, "*.nii.gz")))

        self.total_files = len(self.fileset)
        self.current_file = 0

        print('the number of file set : ', self.total_files)

        self.InsertFileCombo()

    def onPre(self):

        if self.current_file == 0:
            slicer.util.warningDisplay('This is first file', windowTitle='Mangomedcial')
            return

        else:
            self.RemoveCurrentScene()
            self.current_file -= 1

        self.FileComboBox.setCurrentIndex(self.current_file)

    def onNext(self):

        if self.current_file + 1 == self.total_files:
            slicer.util.warningDisplay('This is last file', windowTitle='Mangomedcial')
            return

        else:

            # remove current node
            self.RemoveCurrentScene()
            self.current_file += 1

            self.FileComboBox.setCurrentIndex(self.current_file)

    def onReset(self):

        self.saveDirectory = ""
        self.current_file = 0
        self.total_files = 0
        self.imageDirectory = ""
        self.fileset = []
        self.FileComboBox.clear()

        self.DirButton.setText(self.saveDirectory)

        slicer.util.resetSliceViews()
        slicer.mrmlScene.Clear(0)

    def onDir(self):

        qfiledialog = qt.QFileDialog()
        # tuple_file_paths = qfiledialog.getOpenFileNames()  # Select file(s)
        self.saveDirectory = qfiledialog.getExistingDirectory()  # Select directory

        self.DirButton.setText(self.saveDirectory)

    def onCreateVideo(self):

        if self.saveDirectory == "":

            slicer.util.warningDisplay('Please choose destination folder', windowTitle='Mangomedcial')
            return

        # Specify the directory with your images and the output video filename
        image_basename = os.path.basename(self.fileset[self.current_file])
        image_name = image_basename[:image_basename.find('.nii.gz')]
        video_file = os.path.join(self.saveDirectory, image_name + ".mp4")

        # create png images
        viewNode = slicer.mrmlScene.GetNodeByID("vtkMRMLViewNode1")
        ScreenCapture.ScreenCaptureLogic().capture3dViewRotation(viewNode, -180, 180, 360, 0, self.saveDirectory, "image_%05d.png")

        # Use glob to find all images that match the pattern
        images_pattern = os.path.join(self.saveDirectory, 'image_*.png')
        images_list = sorted(glob.glob(images_pattern))

        # Ensure the images are sorted correctly
        images_list.sort()

        # Create a video clip from the images
        clip = ImageSequenceClip(images_list, fps=60)  # Change fps to your desired frame rate
        clip.write_videofile(video_file)

        # After successfully creating the video, delete the PNG files
        for image_path in images_list:
            os.remove(image_path)
        
        print(f'created video. {video_file}')


    def InsertFileCombo(self):

        for index in range(self.total_files):

            image_basename = os.path.basename(self.fileset[index])
            image_name = image_basename[:image_basename.find('.nii.gz')]

            self.FileComboBox.addItem(image_name)

    def onFileCombo(self, index):

        if self.currentVolumeNode:
            self.RemoveCurrentScene()

        if self.total_files != 0:
            self.current_file = index
            self.LoadFiles()

    def LoadFiles(self):

        if self.imageDirectory == "":

            slicer.util.warningDisplay('Please choose image folder', windowTitle='Mangomedcial')
            return

        elif self.total_files == 0:

            slicer.util.warningDisplay('There are no file to load. Please check image folder and segmentation folder\n\
                image folder : {}\n\
                segmentation folder :{}'.format(self.imageDirectory, self.segDirectory), windowTitle='Mangomedcial')
            return

        else:

            # load volume node and segmentation node
            self.currentVolumeNode = slicer.util.loadVolume(self.fileset[self.current_file])

            # display volume into 3D view
            volRenLogic = slicer.modules.volumerendering.logic()
            displayNode = volRenLogic.CreateDefaultVolumeRenderingNodes(self.currentVolumeNode)
            displayNode.GetVolumePropertyNode().Copy(volRenLogic.GetPresetByName("CT-AAA"))
            displayNode.SetVisibility(True)

            # center 3D view
            layoutManager = slicer.app.layoutManager()
            threeDWidget = layoutManager.threeDWidget(0)
            threeDView = threeDWidget.threeDView()
            threeDView.resetFocalPoint()

            # volume extract threshold 2000
            thresholdValue = 2000
            voxels = slicer.util.arrayFromVolume(self.currentVolumeNode)
            voxels[voxels < thresholdValue] = 0
            slicer.util.arrayFromVolumeModified(self.currentVolumeNode)

            # maximize 3D view
            layoutManager = slicer.app.layoutManager()
            layoutLogic = layoutManager.layoutLogic()

            viewNodes = slicer.util.getNodesByClass("vtkMRMLAbstractViewNode")
            ThreeViewNode = viewNodes[0]

            layoutLogic.MaximizeView(ThreeViewNode)

    def RemoveCurrentScene(self):

        slicer.mrmlScene.Clear(0)

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

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
        # self.setParameterNode(None)

        pass

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""

        pass



#
# ImplantVideoLogic
#


class ImplantVideoLogic(ScriptedLoadableModuleLogic):
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
        return ImplantVideoParameterNode(super().getParameterNode())

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
# ImplantVideoTest
#


class ImplantVideoTest(ScriptedLoadableModuleTest):
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
        self.test_ImplantVideo1()

    def test_ImplantVideo1(self):
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
        inputVolume = SampleData.downloadSample("ImplantVideo1")
        self.delayDisplay("Loaded test data set")

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = ImplantVideoLogic()

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
