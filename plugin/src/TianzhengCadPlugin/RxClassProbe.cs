using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Autodesk.AutoCAD.Runtime;
using Exception = System.Exception;

namespace TianzhengCadPlugin
{
    /// <summary>One resolved runtime class, as read from the live AutoCAD process.</summary>
    internal sealed class RxClassInfo
    {
        public string RequestedClassName { get; set; } = "";
        public bool Found { get; set; }
        public string RuntimeClassName { get; set; } = "";
        public string DxfName { get; set; } = "";
        public string AppName { get; set; } = "";
        public string ParentClass { get; set; } = "";
        public List<string> Ancestry { get; set; } = new();
        public bool IsDerivedFromDbObject { get; set; }
        public bool IsEntity { get; set; }
        public string RuntimeQueryMethod { get; set; } = "";
        public string? Error { get; set; }
    }

    /// <summary>
    /// Read-only RXClass diagnostic.
    ///
    /// WHY REFLECTION: the AutoCAD .NET API exposes <c>RXClass.GetClass(Type)</c> for managed
    /// wrapper types, but a purely native class such as Tianzheng's TDbPipe has no managed
    /// wrapper, so it can only be reached through a name-based lookup whose exact surface
    /// varies between AutoCAD releases. Rather than hard-code a guess, this probe discovers
    /// the available mechanism at runtime and REPORTS which one answered. That keeps the
    /// evidence honest: the result always carries the method that produced it.
    ///
    /// This code creates nothing, opens no document and mutates no database. It only reads
    /// the running process's runtime class registry.
    /// </summary>
    internal static class RxClassProbe
    {
        /// <summary>Resolve one class by name from the live runtime registry.</summary>
        public static RxClassInfo Query(string className)
        {
            var info = new RxClassInfo { RequestedClassName = className };
            if (string.IsNullOrWhiteSpace(className))
            {
                info.Error = "class name is required";
                return info;
            }

            try
            {
                (object? rxClass, string method) = Resolve(className);
                info.RuntimeQueryMethod = method;

                if (rxClass == null)
                {
                    info.Found = false;
                    return info;
                }

                info.Found = true;
                Populate(info, rxClass);
                return info;
            }
            catch (Exception ex)
            {
                info.Error = $"probe failed ({ex.GetType().Name})";
                return info;
            }
        }

        /// <summary>
        /// Try each known name-based lookup in turn. Returns the RXClass (as object, since the
        /// concrete type differs by mechanism) plus a label naming the mechanism used.
        /// </summary>
        private static (object?, string) Resolve(string className)
        {
            // --- 0. The ObjectARX class dictionary. Runtime API discovery on AutoCAD 2026
            //        showed SystemObjects.ClassDictionary : Dictionary, whose At(string)
            //        performs the canonical name lookup. This is the authoritative mechanism.
            try
            {
                object? dictionary = typeof(SystemObjects)
                    .GetProperty("ClassDictionary", BindingFlags.Public | BindingFlags.Static)
                    ?.GetValue(null);

                if (dictionary != null)
                {
                    MethodInfo? at = dictionary.GetType()
                        .GetMethods(BindingFlags.Public | BindingFlags.Instance)
                        .FirstOrDefault(m => m.Name == "At"
                                             && m.GetParameters().Length == 1
                                             && m.GetParameters()[0].ParameterType == typeof(string));
                    if (at != null)
                    {
                        try
                        {
                            object? entry = at.Invoke(dictionary, new object[] { className });
                            if (entry != null) return (entry, "SystemObjects.ClassDictionary.At(string)");
                        }
                        catch (TargetInvocationException)
                        {
                            // Not registered under that name: a definite negative, not an error.
                            return (null, "SystemObjects.ClassDictionary.At(string) -> not registered");
                        }
                    }
                }
            }
            catch (Exception) { /* fall through to the alternatives below */ }

            // --- 1. A static name-based GetClass overload on RXClass, if this release has one.
            foreach (MethodInfo method in typeof(RXClass)
                         .GetMethods(BindingFlags.Public | BindingFlags.Static)
                         .Where(m => m.Name == "GetClass"))
            {
                ParameterInfo[] parameters = method.GetParameters();
                if (parameters.Length == 1 && parameters[0].ParameterType == typeof(string))
                {
                    object? result = method.Invoke(null, new object[] { className });
                    if (result != null) return (result, "RXClass.GetClass(string)");
                }
            }

            // --- 2. The ObjectARX class dictionary, exposed via SystemObjects on some releases.
            object? fromDictionary = TryClassDictionary(className, out string dictMethod);
            if (fromDictionary != null) return (fromDictionary, dictMethod);

            // --- 3. Instantiate by name through RXObject.Create, then read its class. This is a
            //        legitimate runtime-registry lookup: an unregistered name simply fails.
            foreach (MethodInfo method in typeof(RXObject)
                         .GetMethods(BindingFlags.Public | BindingFlags.Static)
                         .Where(m => m.Name is "Create" or "GetClass"))
            {
                ParameterInfo[] parameters = method.GetParameters();
                if (parameters.Length == 1 && parameters[0].ParameterType == typeof(string))
                {
                    try
                    {
                        object? created = method.Invoke(null, new object[] { className });
                        if (created is RXObject rx) return (rx.GetRXClass(), $"RXObject.{method.Name}(string)");
                        if (created != null) return (created, $"RXObject.{method.Name}(string)");
                    }
                    catch (TargetInvocationException) { /* not registered under this name */ }
                }
            }

            return (null, "no name-based lookup mechanism resolved the class");
        }

        /// <summary>Search the runtime class dictionary if this release exposes one.</summary>
        private static object? TryClassDictionary(string className, out string method)
        {
            method = "";
            foreach (Type type in typeof(RXObject).Assembly.GetTypes()
                         .Where(t => t.Namespace == "Autodesk.AutoCAD.Runtime"
                                     && t.Name.Contains("SystemObjects", StringComparison.Ordinal)))
            {
                foreach (PropertyInfo property in type.GetProperties(BindingFlags.Public | BindingFlags.Static))
                {
                    if (!property.Name.Contains("Dictionary", StringComparison.OrdinalIgnoreCase)) continue;
                    object? dictionary = property.GetValue(null);
                    if (dictionary is not IEnumerable entries) continue;

                    foreach (object? entry in entries)
                    {
                        if (entry == null) continue;
                        string? name = NameOf(entry);
                        if (string.Equals(name, className, StringComparison.OrdinalIgnoreCase))
                        {
                            method = $"{type.Name}.{property.Name} enumeration";
                            return entry;
                        }
                    }
                }
            }
            return null;
        }

        /// <summary>Enumerate every runtime class whose name matches a prefix (diagnostic aid).</summary>
        public static List<string> ListClassesWithPrefix(string prefix, int limit = 200)
        {
            var found = new List<string>();
            try
            {
                foreach (Type type in typeof(RXObject).Assembly.GetTypes()
                             .Where(t => t.Namespace == "Autodesk.AutoCAD.Runtime"
                                         && t.Name.Contains("SystemObjects", StringComparison.Ordinal)))
                {
                    foreach (PropertyInfo property in type.GetProperties(BindingFlags.Public | BindingFlags.Static))
                    {
                        if (!property.Name.Contains("Dictionary", StringComparison.OrdinalIgnoreCase)) continue;
                        if (property.GetValue(null) is not IEnumerable entries) continue;

                        foreach (object? entry in entries)
                        {
                            string? name = NameOf(entry);
                            if (name != null && name.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                            {
                                found.Add(name);
                                if (found.Count >= limit) return found;
                            }
                        }
                    }
                }
            }
            catch (Exception) { /* diagnostic aid only */ }
            return found;
        }

        /// <summary>Names of the runtime-namespace types that expose a dictionary, for diagnosis.</summary>
        public static List<string> DescribeAvailableApi()
        {
            var surface = new List<string>();
            try
            {
                foreach (MethodInfo m in typeof(RXClass).GetMethods(BindingFlags.Public | BindingFlags.Static))
                    surface.Add($"RXClass.{m.Name}({string.Join(",", m.GetParameters().Select(p => p.ParameterType.Name))})");
                foreach (MethodInfo m in typeof(RXObject).GetMethods(BindingFlags.Public | BindingFlags.Static))
                    surface.Add($"RXObject.{m.Name}({string.Join(",", m.GetParameters().Select(p => p.ParameterType.Name))})");
                foreach (Type t in typeof(RXObject).Assembly.GetTypes()
                             .Where(t => t.Namespace == "Autodesk.AutoCAD.Runtime" && t.IsPublic
                                         && t.Name.Contains("SystemObjects", StringComparison.Ordinal)))
                {
                    foreach (PropertyInfo p in t.GetProperties(BindingFlags.Public | BindingFlags.Static))
                        surface.Add($"{t.Name}.{p.Name} : {p.PropertyType.Name}");
                }
            }
            catch (Exception) { /* best effort */ }
            return surface.Distinct().OrderBy(x => x).ToList();
        }

        private static string? NameOf(object? entry)
        {
            if (entry == null) return null;
            if (entry is RXClass rxClass) return rxClass.Name;
            PropertyInfo? name = entry.GetType().GetProperty("Name");
            return name?.GetValue(entry) as string;
        }

        /// <summary>Read the class metadata, tolerating members that a given release may not expose.</summary>
        private static void Populate(RxClassInfo info, object rxClass)
        {
            info.RuntimeClassName = Read(rxClass, "Name") ?? "";
            info.DxfName = Read(rxClass, "DxfName") ?? "";
            info.AppName = Read(rxClass, "AppName") ?? "";

            if (rxClass is RXClass typed)
            {
                try
                {
                    RXClass? parent = typed.MyParent;
                    info.ParentClass = parent?.Name ?? "";

                    // Walk the inheritance chain: proof that this is a real DBObject-derived
                    // native class rather than an unrelated registration.
                    RXClass? cursor = parent;
                    int guard = 0;
                    while (cursor != null && guard++ < 32)
                    {
                        info.Ancestry.Add(cursor.Name);
                        if (cursor.Name == "AcDbObject") info.IsDerivedFromDbObject = true;
                        if (cursor.Name == "AcDbEntity") info.IsEntity = true;
                        cursor = cursor.MyParent;
                    }
                }
                catch (Exception) { /* partial metadata is still evidence */ }
            }
        }

        private static string? Read(object target, string propertyName)
        {
            try { return target.GetType().GetProperty(propertyName)?.GetValue(target) as string; }
            catch (Exception) { return null; }
        }
    }
}
