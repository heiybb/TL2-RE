# TL2-Mikuro-Console

Since I am not familiar with WPF, so I decide to create a `Console` version of `TL2-Mikuro` only works for MOD packing.

## Installitaion
Just drop the `TL2-Mikuro-Console.exe` into the same folder of `Editor.exe/Torchlight2.exe`.  

## Known Issue
### Internal
Limited by the logic inside `EditorGuts.dll`, MOD build only accept the projects in `mods` folder

### D3D9RenderSystem
<del>Sometimes the `D3D9RenderSystem::_createRenderWindow` fail to initialize, and not be able to correctly handled.  
Wait for 500ms then try again should be fine, might be related to some memory R/W permission problem.</del>  
Fix via introducing correct console handle getting method  
https://stackoverflow.com/questions/1277563/how-do-i-get-the-handle-of-a-console-applications-window

### MMP Issue
If there is no `.BINLAYOUT` generated for `.LAYOUT`, the `.MPP` files might not be able to generated correctly at the first build.  
Even with GUTS, if there is no `.BINLAYOUT`, at the first you open MOD project with GUTS it will also generate the `.MPP` frist then generate the `.BINLAYOUT`.  
Refer to this [issue](https://github.com/heiybb/TL2-Mikuro/issues/1) in `TL2-Mikuro`.  
<code><del>So if you make changes in the `.LAYOUT` file, and there is `ROOM` or `Particle` chunk in `LAYOUT` file, you will need to build twice.</del></code>

--> Potential fix: manually generate `BINLAYOUT`


## Screenshots

![](https://imgur.com/aXmB3D2.png)
![](https://imgur.com/2tVUdm1.png)