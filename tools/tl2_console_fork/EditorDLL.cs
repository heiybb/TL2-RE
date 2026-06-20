using System.Runtime.InteropServices;
namespace TL2_Mikuro_Console
{
    public class EditorDLL
    {
        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int InitEditor(int hInst, int hWnd);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorRegenPathingData(string dir);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorRegenPathingDataSingleFile(string filename);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetLoadStatus();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorClearLoadingStatus();

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern void EditorLogMessage(string msg, LogEntryLevel level);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetLogDebugOutput(bool bVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool IsA(string UnitType, string BaseUnitType);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetUnitTypeID(string typeName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorForceUIRedraw();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetMainMenuMode(bool bVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSteamLoggedIn();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorSteamGetLastPublishError();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSteamFileIDValid(ulong id);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSteamClearLastPublishError();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSteamWriteFile(string path);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSteamPreShareFile(string path);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSteamPrePublishFile(string path, string title, string desc);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern ulong EditorSteamGetPublishedFileID();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern ulong EditorSteamGetPublishedFilesSteamID(string file);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern ulong EditorSteamGetPublishedFilesModID(string file);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSteamDeletePublishedFile(string path);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSteamDeletePublishedFileByID(long id);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern ulong EditorSteamShareFile(string path);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSteamWrittenFiles();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSteamPublishedFiles();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetSteamPublishedFilesAwaitingStatus();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetSteamFilePubStatus();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool CreateMod(string strModFile, bool bVersion);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string GetModCreateMessage();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSteamRefreshPublishedFileList();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSteamForgetFile(string path);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSteamDeleteFile(string path);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSteamPublishFile(string filename);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSteamUpdatePublishedFile(
          ulong fileID,
          string filename,
          string name,
          string description,
          string previewFile,
          string strTagList,
          string strChangeDesc);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string GetModInfo();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int GetSteamAvailableQuota();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int GetSteamUsedQuota();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int GetSteamTotalQuota();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool IsSteamLoggedOn();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetNewGamePlusMode(bool bVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetBatchCount();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetSelectedObjectsSubMeshesCount();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetUnitType(int ID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetTimeOfDay();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetTimeOfDay(float fTime);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetUpdateTimeOfDay(bool bUpdate);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetShowBlood(bool bval);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetShowBlood();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetShowWeatherEffects(bool bval);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetShowWeatherEffects();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetTimeOfDayMult();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetTimeOfDayMult(float fMult);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int ShutdownEditor();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetActiveSceneID(uint iVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void setObjectControlsVisible(bool val);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorMergeExistingLayoutLink(long iLinkID, long iParentID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorUndo();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorStartUndo();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorEndUndo();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorRedo();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorGetUndoRedoCounts(ref uint Undos, ref uint Redos);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorDeleteAllUndos();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetRedoCount();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetBackgroundColor(float R, float G, float B);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetAlias(string sAlias);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetPreWater(string fileName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetMidWater(string fileName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetPostWater(string fileName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetSkyBox(string fileName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetLevelParticle(string fileName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetShowFog(bool bShowFog);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetShowFog();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetBloom(bool bVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetBloom();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetShowRimlight(bool bShowRimlight);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetShowRimlight();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFogStart(int fogStart);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFogEnd(int fogEnd);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFogColour(float r, float g, float b);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFillLightColour(float r, float g, float b);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetDirectionalLightColour(float r, float g, float b);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetLightMapColour(
          float red,
          float green,
          float blue,
          float alpha);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetTorchlightTexture(string textureName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetShadowFadeTexture(string textureName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetLightMaskTexture(string textureName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFillLightPostion(int x, int y, int z);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFillLightIntensity(float fVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetDirectionalLightIntensity(float fVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetBloomModifier(float fVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetMouseWheelDelta(int iDelta);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetWorkingPlaneHeight(float fHeight);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetSnapToGroundBias(float fBias);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetTempStartPos(float x, float y, float z);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetPlayStartFromMousePos();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetUseTempStartPos(bool bValue);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorTestCameraShake(string cameraShakeName, float fDuration);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAmbientColor(
          ref int red,
          ref int green,
          ref int blue,
          bool bSetColor);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorMaterialAmbientColor(
          ref int red,
          ref int green,
          ref int blue,
          bool bSetColor);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorUpdateMaterialColor();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetWorkingPlaneHeightToSelectedPivot();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetWorkingPlaneHeight();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetPosHSnapSize(float fSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetPosVSnapSize(float fSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetEdtiorLevelDepth();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorRunGodded(bool bGodded);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorAiFreeze(bool bGAiFreeze);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetMonsterAutoSpawn(string strName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetCommandAutoRun(string strCmd);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorLevelPopulate(bool bPopulate);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorMonsterSpawnclass(string SpawnClassName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorBreakablesSpawnclass(string SpawnClassName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorPlayerFile(string strFile);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorLevelPopulateChampions(bool bPopulate);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorLevelPopulateBreakables(bool bPopulate);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorLevelCreatePet(bool bCreatePet);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorCharacterClass(string className);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorActiveQuests(string quests);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorCompletedQuests(string quests);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorPetType(string petType);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorLevelDepth(int iDepth);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetEditorCharacterLevel(int iLevel);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetChunkTemplateBasisSize(float fSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetChunkTemplateWidth(float fSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetChunkTemplateHeight(float fSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetChunkTemplateExits(int Exits);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetChunkTemplateExit(int Exit, float X, float Y, float Z);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetOrientSnapSize(float fSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetFlagState(uint iFlag);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFlagState(uint iFlag, bool bOn);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetTime();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetContext2D();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetContext3D();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorUpdate(int iFlags);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorUpdateObjectControls(float dt);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetObjectUnderMouse();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorFlushKeymanager();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorPostKeyEvent(int keyCode);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetObjectOriginalGuid(long nObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetObjectIDByOriginalGuid(long iOrigID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorSetLookAtObject(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetFarClip(int iVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetFarClip();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetObjectDiagnostic(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorToggleMIPs();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string GetMeshContributions(int iCount);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool GetImageExists(string ImageName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string GetPlayerEffectData();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string GetPlayerStatData();

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorGetObjectProperty(long nObjectID, int nPropertyID);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorGetObjectPropertyArray(
        //  long nObjectID,
        //  int nPropertyID,
        //  ref int nSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetObjectPropertyString(long iObjectID, uint iPropertyID);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void EditorSetObjectProperty(
        //  long nObjectID,
        //  int nPropertyID,
        //  void* pNewValue);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern void EditorSetObjectPropertyArray(
        //  long iObjectID,
        //  int iPropertyID,
        //  int sizeOfArray,
        //  UnionData[] pPropertyValue);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetObjectPropertyArray64(
          long iObjectID,
          int iPropertyID,
          int sizeOfArray,
          long[] pPropertyValue);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorWindowHasFocus(bool bHasFocus);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetIconSheets();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetDescriptorHash();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorCreateObject(
          uint iSceneID,
          uint iDescriptorID,
          long iObjectIDToClone,
          bool bCloneChildren);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorIsObjectHiddenFromEditor(long objID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorIsObjectOutOfBounds(
          long objID,
          float minX,
          float maxX,
          float minY,
          float maxY,
          float minZ,
          float maxZ);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAutomapIcons();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetEquipmentDPSInfo(string itemName, int rolls);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorDeleteObject(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorDeleteAllObjectsInScene(uint iSceneID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetObjectName(long iObjectID, string newName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetObjectName(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetActiveBrushName(string Name);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetActiveBrushName();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorResnapSelectedObjects(bool bResnapOrientation);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorscaleFixer();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorApplyScaleNoise(float fRange, bool bUniform);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorApplyNormalNoise(float fRange);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorApplyRotationNoise(float fRange);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorResetScale();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorResetOrientation();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetOrientationLocal();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetOrientationWorld();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSnapObjectsToGround(bool bSnapNormals);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorToggleDisplayCollision();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetDisplayCollision(bool bVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorObjectExists(long iObjectID);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void EditorSetObjectProperty(
        //  long iObjectID,
        //  uint iPropertyID,
        //  void* pPropertyValue);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorGetObjectProperty(long iObjectID, uint iPropertyID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetListOfItems(
          uint iSceneID,
          long iObjectID,
          uint iPropertyID,
          string seperator);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorFlyToObject(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetObjectSelectedByIndex(int iIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetObjectSelected(long iObjectID, bool bClearFirst);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetObjectIsSelected(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorClearSelectedObjects();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorClearSelectedObjectsExcept(long iObjToIgnore);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetObjectParent(long iObjectID, long iParentID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetRandomAffixesForUnit(uint eUnittype, int iLevel);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetObjectParent(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorPollObjectIDByIndex(uint iSceneID, uint iIndex);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorPollObjects(uint iSceneID, ref int iSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetObjectDescriptorID(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetObjectSceneID(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorFireEvent(uint iSceneID, long iObjectID, uint iEventID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorFireInputEvent(long iObjectID, uint iLogicIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorFireOutputEvent(long iObjectID, uint iLogicIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetSceneVisible(uint iSceneID, bool bVisible);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorGetObjectSnap(
        //  long iObjectID,
        //  ref int iSize,
        //  bool bIncludeHorizontal,
        //  bool bIncludeVertical,
        //  bool bIncludeRotation);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorGetObjectsCreatedThisRender(ref int iSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetObjectsUnderMouse2D();

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorGetObjectsInLevel(ref int iSize);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorGetObjectsDeletedThisRender(ref int iSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadAllAssets();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadInventoryData();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadStats();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadWaypoints();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadModFileFilter();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string GetEnabledModNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string GetModNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void SetModEnabled(string ModName, bool bEnabled);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadCinematics();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadAffixes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAddLocalFile(string file);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadBrushes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadEditorLayoutLinks();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadWardrobeGroups();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadMissiles();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadPlayer(string file);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadProp(string file);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadMonster(string file, bool bReloadDescriptor);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadMonsterDescriptors();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadUnitTriggerDescriptors();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadItem(string file);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadAllUnits();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadTextures();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadMaterials();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadItemSets();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadUnitThemes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadEffectsData();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadUnittypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadThemes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadAliases();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadLevelFeatureTags();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadEditorParticles();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadRecipes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadTriggerableActions();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadQuests();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void reloadSpawnClasses();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void rollRoomPiece(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void increamentRoomPieceVariation(long iObjectID, bool bForward);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorMakeGuid();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorFileExists(string file);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorConvertLayoutToNewTileset(string tilesetName, string layoutfile);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorSaveScene(uint sceneID, string fileAndPath, bool bSelectedOnly);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorCEGUIScene(uint sceneID, string fileAndPath);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorLoadScene(uint sceneID, string fileAndPath, bool bClearFirst);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorLoadScene(
          uint sceneID,
          string fileAndPath,
          bool bClearFirst,
          long iParentGuid);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorStoreClipboardTransformation();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorApplyClipboardTransformation();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorTimelineSetPercentDone(long nTimelineObjectID, float fPercent);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorTimelineUpdate(long nTimelineObjectID, float dt);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorTimelineAddProperty(
          long nTimelineObjectID,
          long nObjectID,
          int nPropertyID,
          bool bIsEventProperty);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorTimelineRemoveProperty(
          long iTimelineObjectID,
          long iObjectID,
          int iPropertyID,
          bool bIsEventProperty);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorTimelineAddPointToProperty(
          long iTimelineObjectID,
          long iObjectID,
          int iPropertyID,
          bool bIsEventProperty);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorTimelineSetPropertyInterpType(
          long nTimelineObjectID,
          long nObjectID,
          int nPropertyID,
          string nameType);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorTimelineGetPropertyInterpType(
          long nTimelineObjectID,
          long nObjectID,
          int nPropertyID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorTimelineRemovePointFromProperty(
          long iTimelineObjectID,
          long iObjectID,
          int nPropertyID,
          int iPointID,
          bool bIsEventProperty);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void EditorTimelineSetPropertyPointValue(
        //  long iTimelineObjectID,
        //  long iObjectID,
        //  int iPropertyID,
        //  int iPointID,
        //  void* pValue);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern void EditorTimelineSetPropertyPointValueArray(
        //  long iTimelineObjectID,
        //  long iObjectID,
        //  int iPropertyID,
        //  int iPointID,
        //  int iSize,
        //  UnionData[] pValue);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorTimelineSetPropertyPointTimePercent(
          long iTimelineObjectID,
          long iObjectID,
          int iPropertyID,
          int iPointID,
          float fTimePercent,
          bool bIsEventProperty);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorTimelineGetTimePercentAtPoint(
          long iTimelineObjectID,
          long iObjectID,
          int iPropertyID,
          int nPointID,
          bool bIsEventProperty);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorTimelineGetValueAtPoint(
        //  long iTimelineObjectID,
        //  long iObjectID,
        //  int iPropertyID,
        //  int iPointID);

        //[DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        //public static extern unsafe void* EditorTimelineGetValueAtPointArray(
        //  long iTimelineObjectID,
        //  long iObjectID,
        //  int iPropertyID,
        //  int iPointID,
        //  ref int iSize);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorTimelineGetObjectIDInTimelineByIndex(
          long iTimelineObjectID,
          int iIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorTimelineGetPropertyIDForObjectInTimelineByIndex(
          long iTimelineObjectID,
          long iObjectID,
          int iPropertyIndex,
          ref bool bIsEventProperty);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorTimelineGetPointIDInTimelinePropertyByIndex(
          long iTimelineObjectID,
          long nObjectID,
          int iPropertyID,
          int iPointIndex,
          bool bIsEventProperty);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetLogicFuncId(
          uint iSceneID,
          uint iDescriptorID,
          string LogicFuncRefName,
          bool bIsInputFunc);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorCreateLogicObject(long nLogicGroupID, long nObjectIDToRef);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorCreateLogicLink(
          long nLogicGroupID,
          uint nLogicObjectIDOutput,
          uint nLogicObjectIDInput,
          uint nLogicOutputIndex,
          uint nLogicInputIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorDeleteLogicObject(long nLogicGroupID, int nLogicObjectIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorDeleteLogicLink(
          long nLogicGroupID,
          uint nLogicObjectIndex,
          uint nLogicLinkIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetCountOfLogicLinksInLogicObject(
          long nLogicGroupID,
          uint nLogicObjectIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetLogicLinkOutputFunctionID(
          long nLogicGroupID,
          uint nLogicObjectIndex,
          uint nLogicLinkIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetLogicLinkInputFunctionID(
          long nLogicGroupID,
          uint nLogicObjectIndex,
          uint nLogicLinkIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetLogicObjectIDLinkingTo(
          long nLogicGroupID,
          uint nLogicObjectIndex,
          uint nLogicLinkIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern uint EditorGetCountOfLogicObjectsInLogicGroup(long nLogicGroupID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetObjectIDRefedInLogicObject(
          long nLogicGroupID,
          uint nLogicObjectIndex);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetLogicObjectPosition(
          long nLogicGroupID,
          uint nLogicObjectIndex,
          int x,
          int y);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetLogicObjectPosition(
          long nLogicGroupID,
          uint nLogicObjectIndex,
          ref int x,
          ref int y);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorInvokeOutputFunction(
          long nLogicGroupID,
          uint nLogicObjectIDOutput,
          uint nOutputFunctionID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetDebugOutput();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetModelAnimationLengthSeconds(
          long nObjectID,
          string animationName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadModelAnimations(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAnimationKeyTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetUnitThemes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetShowSoundHelpers(bool bVal);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorHideCharacterDiagnosticShapes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorHideCharacterColliders();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAliaseNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetFeatureNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetWardrobeSets();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetDamageTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAITypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetUnitsByUnittype(string UnitType);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetUnits();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSpawnClasses();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetDungeons();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadDungeons();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetCinematics();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorAutomapTiles();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetInventorySlotNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetInventoryContainerNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetWardrobeFeatureNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetMissiles();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetDialogMenus();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetMaterialNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadUIMenus();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetMeshNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetTextureNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetTextureMemoryUsage();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetMaterialMemoryUsage();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetMeshMemoryUsage();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetDescriptorNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetDescriptorPropertyNames(string descName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetBrushes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadSkill(string filename);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSkills();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSkillEventTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetSkillEventTypeCloneableDefault(string EventType);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAffixes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSkillTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSkillTargetTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetDungeonTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSkillEffectAndAffixTargetTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetGameEventTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetCharacterEventTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetStatEventTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetEventCreatorTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetStatTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetStatWatchTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetStatWatcherTargetTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetStatNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSkillActivationTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetQuests();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSets();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetUnitTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetUnitTypesOfUnitType(string typeName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAlignments();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAIFlags();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetGraphNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSkeletonBoneList(long nObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetCharacterBonePush(
          long iObjID,
          string boneName,
          float fVal,
          bool bUpdateWardrobe);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorUpdateCharacterWardrobe(long iObjID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAttachBoneNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetAnimationNameByPath(long iObjectID, string animationPath);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetActiveAnimationPaused(long iObjectID, bool bPaused);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetActiveAnimationTimePosition(
          long iObjectID,
          float fTimePosition);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetActiveAnimationTimePosition(long iObjectID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSoundCategories();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorPlaySound(
          string fileName,
          float vol,
          float volVar,
          float freqVar);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorStopSound(int channelID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorPlayMusic(string fileName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorStopMusic();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSoundNamesByCategory(string categoryName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetSoundNames();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadSoundData();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetPlayMusicInGame(bool bPlayMusic);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetMuted(bool bMuted);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGetMuted();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorResetCamera(float x, float y, float z);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetPOVVelocityMult(float fMult);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetLightDirectional(float x, float y, float z);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorParticleMovementConfig(
          ref float fDuration,
          ref float fRadius,
          bool bSetValues);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetIngameRes(int width, int height);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorGetIngameRes(ref int width, ref int height);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetModPriority(string modDirectory, int iPriority);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorCreateMod(string modDirectory);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string spawnClassTest(
          string spawnclass,
          string beneficiaryUnitType,
          int level,
          int times,
          bool bNoCountRange,
          bool bIgnoreLevelRange,
          int iMagicFind);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void spawnUnit(long unitGUID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string levelTemplateTest(string templatePath, int seed);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorClearEditorThemes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAddEditorThemes(long iThemeId);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern long EditorGetThemeID(string themeName);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorRollAndDisplayRules(string file, int iSeed);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetShowMouseOverInfo(bool bShowInfo);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAlignLefts();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAlignRights();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAlignTops();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAlignBottoms();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorEqualizeWidths();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorEqualizeHeights();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetUIObjectSizeToImageSize();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetUIScale(float fScale);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetUIScale();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetUIOffset(float fUIOffsetX, float fUIOffsetY);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetUIOffsetX();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern float EditorGetUIOffsetY();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorGetUIOffsetResolution(ref int iWidth, ref int iHeight);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGroupNodeHasTheme(long objID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern bool EditorGroupNodeIsFeatureTagged(long objID);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorDumpStatsAverages();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void doRoomPieceToLayoutLinkMagic();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorAddLocalFilesFromModDirectory(string strPath);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorRemoveLocalFilesFromModDirectory();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorReloadUnitTypes();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorSetWorkingMod(string strPath);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern void EditorUncompressPak(string strPathToPak, string strPathToUncompressTo);

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern string EditorGetUncompressMessage();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetUncompressFileCount();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorGetUncompressFileCountMax();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorPakIsOld();

        [DllImport("EditorGuts.dll", CharSet = CharSet.Unicode)]
        public static extern int EditorStampPakVersion();
    }
}
